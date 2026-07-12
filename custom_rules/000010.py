# custom_rules/000010.py — seq_no=000010(맥도날드) 전용 커스텀 수집 규칙
import time
import random

from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException


def render(driver, selectors, items: dict) -> list[dict]:
    """매장 목록을 하나씩 클릭 → 상세 팝업에서 필드 추출 → 닫기 버튼 클릭."""
    result = []

    for row in selectors:
        time.sleep(random.uniform(1.0, 4.0))  # 랜덤하게 타임 슬립 설정
        row.click()

        data = {}
        for column_name, relative_xpath in items.items():
            try:
                data[column_name] = driver.find_element(By.XPATH, relative_xpath).text
            except NoSuchElementException:
                data[column_name] = None
        result.append(data)

        time.sleep(random.uniform(1.0, 4.0))  # 랜덤하게 타임 슬립 설정

        # 닫기 버튼 클릭
        driver.find_element(By.XPATH, '//*[@id="container"]/div[2]/section/div/button').click()

    return result
