# custom_rules/render/000013.py — seq_no=000013(네이버) 전용 커스텀 로그인 규칙
import time
import random

from selenium.webdriver.common.by import By


def login(driver, login_info: dict) -> None:
    # 로그인 박스 클릭
    driver.find_element(By.ID, "account").click()

    # 아이디
    id_input = driver.find_element(By.ID, "id")
    time.sleep(random.uniform(1.0, 4.0))  # 랜덤하게 타임 슬립 설정
    id_input.click()
    time.sleep(random.uniform(1.0, 4.0))  # 랜덤하게 타임 슬립 설정
    id_input.send_keys(login_info["id"])

    # 비밀번호
    pwd_input = driver.find_element(By.ID, "pw")
    time.sleep(random.uniform(1.0, 4.0))  # 랜덤하게 타임 슬립 설정
    pwd_input.click()
    time.sleep(random.uniform(1.0, 4.0))  # 랜덤하게 타임 슬립 설정
    pwd_input.send_keys(login_info["password"])

    driver.find_element(By.ID, "log.login").click()
