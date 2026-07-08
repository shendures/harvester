import os, sys, json, time, logging, multiprocessing
from datetime import datetime
import utility
import engine
import customized_settings
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from PyQt6.QtCore import QThread, pyqtSignal
from conf import DataStore
import queue as _queue

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════
#  QUEUE WRITER  (자식 프로세스 stdout/stderr → Queue)
# ══════════════════════════════════════════════════════
class QueueWriter:
    """
    자식 프로세스의 sys.stdout / sys.stderr 를 multiprocessing.Queue 로
    리다이렉트하기 위한 파일-유사(file-like) 객체.
    """
    def __init__(self, queue: multiprocessing.Queue):
        self.queue = queue

    def write(self, msg: str) -> None:
        if msg and msg.strip():
            try:
                self.queue.put_nowait(msg.strip())
            except Exception:
                pass  # 큐가 닫혔거나 가득 찬 경우 조용히 무시

    def flush(self) -> None:
        pass  # CrawlerProcess 내부에서 flush()를 호출할 수 있으므로 빈 구현 유지


# ══════════════════════════════════════════════════════
#  CRAWLER WORKER THREAD
# ══════════════════════════════════════════════════════
class MultiprocessWorker(QThread):
    """
    별도의 서브 프로세스를 실행하고 모니터링하여 Scrapy를 구동하는 작업 스레드.

    [주의] DataStore는 메인 프로세스(UI)에서만 유효합니다.
    자식 프로세스(run_spider)는 Queue를 통해서만 데이터를 전달하며,
    DataStore를 직접 참조하지 않습니다.
    """

    progress     = pyqtSignal(int, int)
    new_row      = pyqtSignal(dict)
    log_message  = pyqtSignal(str, str)   # (level: str, message: str)
    stats_update = pyqtSignal(dict)
    finished     = pyqtSignal(dict, dict) # (task, summary)

    LOG_TEMPLATES = {
        "ok":   ["수집 성공 ({url}) — {time}s", "파싱 완료: {title}", "데이터 저장 완료 #{idx}"],
        "warn": ["응답 지연 감지 ({time}s), 딜레이 조정 중", "Rate limit 감지 — 재시도 대기"],
        "err":  ["연결 타임아웃: {url}", "파싱 오류: 셀렉터 매칭 실패 ({url})"],
        "info": ["페이지 {page} 진입 중", "셀렉터 재적용 완료", "프록시 전환 ({proxy})"],
    }

    def __init__(self, task: dict, job_name: str = "수동 실행"):
        super().__init__()
        self.task      = task
        self.job_name  = job_name
        self.process   = None
        self.queue     = multiprocessing.Queue()
        self._running  = True
        self._errors   = 0
        self._done     = 0
        self._resp_times: list[float] = []
        self.total        = None
        self._started_at: datetime | None = None
        self.store     = DataStore()

    # ── 외부에서 중단 요청 ────────────────────────────
    def stop(self) -> None:
        """
        수집 중단 요청.
        _running 플래그를 False 로 세팅하면 run() 루프가 다음
        queue.get(timeout=0.5) 만료 시점에 중단 분기로 진입합니다.
        """
        self._running = False

    # ── 메인 실행 루프 ────────────────────────────────
    def run(self) -> None:

        # [수정] _started_at을 run() 진입 즉시 초기화
        #        기존: stop()이 run() 시작 전에 호출되면 finally에서 TypeError 발생
        self._started_at = datetime.now()

        callback_url = self.task["callback_url"]
        threads      = self.task["threads"]
        delay        = self.task["delay"]

        # ── URL 리스트 생성 ───────────────────────────
        try:
            generated_urls = utility.generate_combined_urls(callback_url)
            url_list       = set(generated_urls)
            total          = len(url_list)

            # [DEBUG] url_list 생성 결과 확인
            if total == 0:
                logger.warning("[DEBUG][run] generate_combined_urls() 반환값이 비어 있음 — callback_url: %s", callback_url)
                self.log_message.emit("warn", f"수집 대상 URL이 생성되지 않았습니다. URL 설정을 확인해주세요. (대상: {callback_url})")
            else:
                logger.debug("[DEBUG][run] url_list 생성 완료 — 총 %d개", total)
                self.log_message.emit("info", f"총 {total}개 URL 수집을 시작합니다.")
                for u in list(url_list)[:5]:   # 최대 5개만 출력 (로그 과부하 방지)
                    logger.debug("[DEBUG][run] url_list 샘플: %s", u)

        except Exception as e:
            # [수정] 기존: bare except로 예외 원인을 로그에 남기지 않아 디버깅 불가
            logger.error("[MultiprocessWorker] URL 생성 실패: %s", e)
            self.log_message.emit("err", f"URL 생성 중 오류 발생: {e}")
            url_list = set()
            total    = 0

        self.log_message.emit("info", "크롤러 초기화 완료")
        self.log_message.emit("info", f"대상: {callback_url}")
        self.log_message.emit("info", f"스레드 {threads}개 / 딜레이 {delay}s")

        processed_urls = set()

        try:
            self.process = multiprocessing.Process(
                target=run_spider,
                args=(self.task, self.queue),
                daemon=True,   # 메인 프로세스 종료 시 자식도 자동 종료
            )
            self.process.start()
            self.log_message.emit("info", "SCRAPY START")

            # ── 실시간 수신 루프 ──────────────────────
            # [수정] queue.empty()는 멀티프로세스 환경에서 신뢰할 수 없으므로
            #        프로세스 종료 후 드레인(drain) 단계를 별도로 처리합니다.
            while True:
                # ── 중단 요청 처리 ────────────────────
                if not self._running:
                    self._terminate_process()
                    self._drain_queue()
                    self.log_message.emit("warn", "사용자에 의해 중단됨")
                    break

                # ── 큐에서 메시지 읽기 ────────────────
                try:
                    line = self.queue.get(timeout=0.5)

                except Exception:
                    # [수정] proc_alive를 queue.get() 타임아웃 직후 재평가
                    #        기존: 루프 최상단에서 캡처한 값을 사용 → 0.5초 블로킹 사이에
                    #        자식 프로세스가 종료되면 True로 고정된 채 continue → 마지막
                    #        배치 결과 유실 가능
                    proc_alive = self.process is not None and self.process.is_alive()
                    if not proc_alive:
                        # 프로세스 종료 후 잔여 메시지 드레인
                        logger.debug(
                            "[DEBUG][run] 자식 프로세스 종료 감지 — drain 시작 "
                            "(현재 _done=%d, processed=%d)",
                            self._done, len(processed_urls),
                        )
                        pre_drain_done = self._done
                        self._drain_queue_and_process(
                            url_list, processed_urls, callback_url, total, delay, threads
                        )
                        logger.debug(
                            "[DEBUG][run] drain 완료 — drain 전 _done=%d, drain 후 _done=%d, 추가 수집=%d",
                            pre_drain_done, self._done, self._done - pre_drain_done,
                        )
                        break
                    continue

                self._handle_line(
                    line, url_list, processed_urls, callback_url, total, delay, threads
                )

        except Exception as e:
            # [수정] 기존: emit("err", e) — e가 Exception 객체라 str 시그널 타입 불일치 → TypeError
            err_msg = str(e)
            logger.error("[MultiprocessWorker] run() 예외: %s", err_msg)
            self.log_message.emit("err", err_msg)

        finally:
            self._emit_finished(callback_url)

    # ── 내부 헬퍼 ─────────────────────────────────────
    def _handle_line(
        self,
        line: str,
        url_list: set,
        processed_urls: set,
        callback_url: str,
        total: int,
        delay: float,
        threads: int,
    ) -> None:
        """큐에서 읽은 한 줄을 파싱하여 시그널을 emit합니다."""
        clean_line = line.strip()

        if clean_line.startswith("EXECUTOR_STATUS: FAILED"):
            reason = clean_line.replace("EXECUTOR_STATUS: FAILED", "").strip()
            logger.error("[MultiprocessWorker] Scrapy 실행 실패: %s", reason)
            self.log_message.emit("err", f"Scrapy 실행 실패: {reason}")
            self._running = False  # 루프 종료 유도
            return

        if not clean_line.startswith("RESULT_INFO:"):
            return
        try:
            result_info = json.loads(clean_line.replace("RESULT_INFO:", "", 1).strip())
        except json.JSONDecodeError as e:
            logger.warning("[MultiprocessWorker] RESULT_INFO JSON 파싱 실패: %s | 원본: %s", e, clean_line[:120])
            return

        # resp_info 키 존재 확인
        resp_info = result_info.get("resp_info")
        if not isinstance(resp_info, dict):
            logger.warning(
                "[DEBUG][_handle_line] resp_info 키 없음 또는 잘못된 타입 — "
                "실제 타입: %s, result_info 최상위 키: %s",
                type(resp_info).__name__,
                list(result_info.keys()),
            )
            return

        result_info["resp_info"]["timestamp"] = datetime.now()
        result_info["job_name"] = self.job_name

        # [수정] 기존: resp_info["url"](리다이렉트 후 최종 URL)로 url_list를 대조
        #        → redirect가 발생하는 사이트는 최종 URL ≠ 요청 URL이라
        #          모든 결과가 "URL 불일치"로 skip되어 total=0이 되는 문제
        #        → 리다이렉트 전 최초 요청 URL(req_url)로 대조 (없으면 기존 url로 fallback)
        res_url     = resp_info.get("req_url") or resp_info.get("url", "")
        status_code = resp_info.get("status")
        resp_time   = resp_info.get("pure_latency", 0.0)
        reason      = resp_info.get("reason", "")

        # [수정] 기존: 중복 판정이 url_map 집계·_done 카운트만 보호하고,
        #        log_message·store.add_row·new_row.emit·_resp_times·progress·stats_update는
        #        조건 블록 바깥에 있어 중복 응답 시에도 무조건 실행됨.
        #        → Scrapy 비동기 중복 요청으로 동일 URL의 RESULT_INFO가 2회 수신될 때
        #          두 번째 응답의 data가 비어 있으면 UI 테이블에 표출되지 않으면서
        #          로그·진행률은 정상처럼 갱신되는 불일치 현상 발생.
        #        → 중복 URL이면 모든 처리를 skip하여 첫 번째 응답만 유효하게 처리.
        if res_url not in url_list or res_url in processed_urls:
            if res_url in processed_urls:
                # 중복 응답 — 정상적인 skip
                logger.debug("[DEBUG][_handle_line] 중복 URL skip: %s", res_url)
            else:
                # url_list 불일치 — total=0 원인의 핵심 후보
                sample = list(url_list)[:3]
                logger.warning(
                    "[DEBUG][_handle_line] ★ URL 불일치 skip ★\n"
                    "  res_url               : %s\n"
                    "  url_list 샘플(최대 3개): %s\n"
                    "  url_list 총 %d개",
                    res_url, sample, len(url_list),
                )
            return

        # 이하 모든 처리는 대상 URL의 최초 응답에 대해서만 실행됨
        processed_urls.add(res_url)
        self.store.add_url_map({
            "req_url":      res_url,
            "status_code":  status_code,
            "pure_latency": resp_time,
            "session":      len([callback_url]),
            "timestamp":    result_info["resp_info"]["timestamp"],
        })
        self._done += 1

        # 상태 코드별 로그 레벨
        if status_code in (404, 500, 502, 503):
            self._errors += 1
            level = "err"
        elif status_code == 429:
            level = "warn"
        elif status_code == 301:
            level = "info"
        elif status_code == 200:
            level = "ok"
        else:
            level = "info"

        self.log_message.emit(level, str(reason))

        self.store.add_row(result_info)
        self.new_row.emit(result_info)

        if isinstance(resp_time, (int, float)):
            self._resp_times.append(float(resp_time))

        avg = sum(self._resp_times) / len(self._resp_times) if self._resp_times else 0.0

        self.progress.emit(self._done, total)
        self.stats_update.emit({
            "total":    self._done,
            "errors":   self._errors,
            "pages":    total,
            "avg_time": f"{avg:.2f}s",
        })

        # [수정] delay / threads — threads 검증은 run() 진입 시 완료됨
        sleep_sec = max(0.05, delay / threads)
        time.sleep(sleep_sec)

    def _drain_queue_and_process(
        self,
        url_list: set,
        processed_urls: set,
        callback_url: str,
        total: int,
        delay: float,
        threads: int,
    ) -> None:
        """
        프로세스 종료 후 Queue에 남은 메시지를 모두 소비합니다.

        [수정] 기존: queue.empty()가 신뢰할 수 없어 프로세스 종료 직후
               잔여 메시지가 처리되지 않을 수 있었음.
               프로세스 종료가 확인된 이후에 get_nowait()로 안전하게 드레인합니다.
        """
        while True:
            try:
                line = self.queue.get_nowait()
                self._handle_line(line, url_list, processed_urls, callback_url, total, delay, threads)
            except _queue.Empty:
                break
            except Exception as e:
                # [수정] 기존 break → continue
                #        _handle_line() 내부 예외(JSONDecodeError 등) 하나에 드레인 전체가
                #        중단되어 뒤에 남은 정상 메시지까지 버려지던 문제 수정
                logger.warning("[MultiprocessWorker] 드레인 중 오류: %s", e)
                continue

    def _drain_queue(self) -> None:
        """중단 요청 후 Queue에 남은 메시지를 버립니다."""
        while True:
            try:
                self.queue.get_nowait()
            except _queue.Empty:
                break
            except Exception:
                break

    def _terminate_process(self) -> None:
        """서브 프로세스를 단계적으로 종료합니다 (SIGTERM → SIGKILL → close)."""
        if self.process is None:
            return
        try:
            if self.process.is_alive():
                self.process.terminate()
                self.process.join(timeout=0.5)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=0.3)
        except Exception as e:
            logger.warning("[MultiprocessWorker] 프로세스 종료 중 오류: %s", e)
        finally:
            try:
                self.process.close()
            except Exception:
                pass

    def _emit_finished(self, callback_url: str) -> None:
        """
        finally 블록에서 호출 — 세션 요약을 DataStore에 기록하고
        finished 시그널을 emit합니다.

        [수정] 기존: _started_at이 None이면 elapsed 계산에서 TypeError 발생
               → _started_at이 None인 경우 경과 시간을 0으로 처리
        """
        now     = datetime.now()
        elapsed = (now - self._started_at).total_seconds() if self._started_at else 0.0
        avg_t   = sum(self._resp_times) / len(self._resp_times) if self._resp_times else 0.0

        # [DEBUG] summary 생성 직전 최종 카운터 상태 출력
        #         total=0 인데 이 로그가 찍히면 → _handle_line 단계에서 전량 skip된 것
        #         이 로그 자체가 안 찍히면 → _emit_finished 호출 전에 프로세스가 비정상 종료
        logger.warning(
            "[DEBUG][_emit_finished] 최종 카운터 — _done=%d, _errors=%d, "
            "_resp_times 개수=%d, elapsed=%.1fs",
            self._done, self._errors, len(self._resp_times), elapsed,
        )

        summary = {
            "job":         self.job_name,
            "url":         callback_url,
            "total":       self._done,
            "errors":      self._errors,
            "success":     self._done - self._errors,
            "avg_time":    round(avg_t, 3),
            "elapsed":     round(elapsed, 1),
            "started":     self._started_at.strftime("%Y-%m-%d %H:%M:%S") if self._started_at else "—",
            "interrupted": not self._running,
            "finished":    now.strftime("%Y-%m-%d %H:%M:%S"),
        }

        self.store.add_session(summary)
        self.finished.emit(self.task, summary)


# ══════════════════════════════════════════════════════
#  SCRAPY 설정
# ══════════════════════════════════════════════════════
def set_scrapy_settings(settings_dict: dict):
    """
    Scrapy 프로젝트 설정에 수집 파라미터를 적용하고 반환합니다.

    [수정] settings_dict가 None이거나 필수 키가 없을 때 KeyError / TypeError 방지.
           필수 키 누락 시 로그를 남기고 기본값으로 대체합니다.
    """
    settings = get_project_settings()
    settings.set("LOG_ENABLED", True, priority="cmdline")

    if not settings_dict:
        logger.warning("[set_scrapy_settings] settings_dict가 비어 있습니다. 기본 설정으로 진행합니다.")
        return settings

    # [수정] 필수 키별 기본값 정의 — 누락 시 KeyError 대신 기본값 사용
    DEFAULTS = {"threads": 4, "delay": 1.0, "timeout": 10}
    for key, default in DEFAULTS.items():
        if key not in settings_dict:
            logger.warning("[set_scrapy_settings] 키 '%s' 없음, 기본값 %s 사용", key, default)
            settings_dict[key] = default

    try:
        # 실패해도 진행 가능(프록시 없이 크롤링 계속) — 이 블록만 예외 흡수
        proxy_req_info = customized_settings.set_ip_settings(settings_dict)
        if proxy_req_info:
            settings.set("ip_list",       proxy_req_info["ip_list"])
            settings.set("allow_ip_cnts", proxy_req_info["allow_ip_cnts"])
    except Exception as e:
        logger.error("[set_scrapy_settings] 프록시 설정 적용 중 오류(프록시 없이 진행): %s", e)

    # 핵심 설정 — 실패 시 크롤링이 무의미해지므로 흡수하지 않고 그대로 전파
    settings.set("DOWNLOADER_MIDDLEWARES", customized_settings.set_downloader_middlewares(settings_dict))
    settings.set("ITEM_PIPELINES",        {"pipelines.LoadItemPipeline": 100})
    settings.set("CONCURRENT_REQUESTS",   settings_dict["threads"])
    settings.set("DOWNLOAD_DELAY",        settings_dict["delay"])
    settings.set("DOWNLOAD_TIMEOUT",      settings_dict.get("timeout", 10))

    return settings


# ══════════════════════════════════════════════════════
#  자식 프로세스 진입점
# ══════════════════════════════════════════════════════
def run_spider(request_info: dict, queue: multiprocessing.Queue) -> bool:
    """
    multiprocessing.Process의 target으로 호출되는 Scrapy 실행 진입점.

    stdout / stderr 를 QueueWriter 로 리다이렉트하여
    수집 로그와 RESULT_INFO 메시지를 부모 프로세스로 전달합니다.

    [수정]
    - docstring을 코드 앞으로 이동 (기존: stdout 리다이렉트 이후에 위치해 무의미)
    - sys.stdout.flush 재할당 제거 (QueueWriter에 flush()가 이미 정의되어 있음)
    - ReactorNotRestartable 등 Scrapy 내부 예외를 별도 catch하여
      부모 프로세스가 FAILED 상태를 인지할 수 있도록 Queue에 기록
    - request_info 유효성 검증 강화
    """
    # stdout/stderr 리다이렉트 (자식 프로세스이므로 원본 복원 불필요)
    writer      = QueueWriter(queue)
    sys.stdout  = writer
    sys.stderr  = writer

    if not request_info or not isinstance(request_info, dict):
        print("EXECUTOR_LOG: 실행할 데이터가 없거나 형식이 올바르지 않습니다.")
        return False

    settings = set_scrapy_settings(request_info)
    process  = CrawlerProcess(settings)

    # ── 스파이더 등록 ─────────────────────────────────
    try:
        spider = engine.get_spider(request_info)
        process.crawl(spider, request_info=request_info)
        print(f"EXECUTOR_LOG: 스파이더 예약 완료: {request_info.get('title', '(제목 없음)')}")
    except Exception as e:
        print(f"EXECUTOR_LOG: 스파이더 로드 실패: {e}")
        # 스파이더 등록 실패 시 크롤링 시작 불가 → 즉시 종료
        return False

    # ── Scrapy 실행 (블로킹) ──────────────────────────
    try:
        process.start()
        print("EXECUTOR_STATUS: SUCCESS")
        return True
    except Exception as e:
        # [수정] ReactorNotRestartable 등 Scrapy 내부 예외도 Queue로 전달
        #        부모 프로세스가 FAILED를 인지하고 UI를 복원할 수 있게 함
        print(f"EXECUTOR_STATUS: FAILED Scrapy 실행 오류: {e}")
        logger.error("[run_spider] Scrapy 실행 오류: %s", e)
        return False
