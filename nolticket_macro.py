# -*- encoding:utf8 -*-

import sys
import time
import threading
import traceback
import winsound

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from urllib.request import urlretrieve
from bs4 import BeautifulSoup
from selenium.webdriver.common.action_chains import ActionChains
from PIL import Image
import numpy as np

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QSpinBox, QPushButton,
    QButtonGroup, QTextEdit, QMessageBox
)

EXPIRE_DATE = "~26.09.30"


# ──────────────────────────────────────────────
#  신호 브릿지
# ──────────────────────────────────────────────
class Signals(QObject):
    log_signal      = pyqtSignal(str)    # 로그 추가
    captcha_signal  = pyqtSignal()       # 보안문자 입력창 표시 요청
    input_hide      = pyqtSignal()       # 보안문자 입력창 숨김


# ──────────────────────────────────────────────
#  매크로 스레드
# ──────────────────────────────────────────────
class MacroThread(QThread):
    def __init__(self, driver, login_type, user_id, user_pw, delay, signals):
        super().__init__()
        self.driver     = driver
        self.login_type = login_type
        self.user_id    = user_id
        self.user_pw    = user_pw
        self.delay      = delay
        self.sig        = signals
        self._stop      = False
        self._pause     = False

        self._captcha_event  = threading.Event()
        self._captcha_answer = ""

    def stop(self):
        self._stop = True

    def pause(self):
        self._pause = not self._pause
        return self._pause

    def set_captcha_answer(self, text):
        self._captcha_answer = text
        self._captcha_event.set()

    def log(self, msg):
        now = time.strftime("%Y/%m/%d %H:%M:%S")
        self.sig.log_signal.emit(f"[{now}] {msg}")

    def _wait(self, sec):
        deadline = time.time() + sec
        while time.time() < deadline:
            if self._stop: raise InterruptedError
            while self._pause:
                time.sleep(0.1)
                if self._stop: raise InterruptedError
            time.sleep(0.05)

    # ── 사용자 입력 대기 (보안문자/등급선택 공용)
    def _ask_user(self, timeout=120):
        self._captcha_event.clear()
        self.sig.captcha_signal.emit()
        if not self._captcha_event.wait(timeout=timeout):
            return None
        answer = self._captcha_answer
        self.sig.input_hide.emit()
        return answer

    # ── 페이지에서 구역 목록 읽기
    def _get_zones(self, grade_idx):
        """
        인터파크 좌석 선택 페이지에서 구역 이름 목록 반환.
        grade_idx: 0=모두, 1~6=특정등급 인덱스
        """
        GRADE_KW = ["스탠딩R","스탠딩S","지정석R","지정석S","지정석A","지정석B"]
        driver = self.driver
        zones = []

        driver.switch_to.default_content()
        for fid in ["ifrmSeat", "mainFrame"]:
            try:
                driver.switch_to.frame(driver.find_element(By.ID, fid))
                break
            except:
                pass

        try:
            # 우측 패널 좌석등급 목록 파싱
            bs = BeautifulSoup(driver.page_source, "html.parser")

            # 구역 area 태그 (좌석 지도)
            areas = bs.find_all("area")
            for area in areas:
                title = area.get("title") or area.get("alt") or ""
                if not title:
                    continue
                if grade_idx == 0:
                    zones.append(title)
                else:
                    kw = GRADE_KW[grade_idx - 1] if grade_idx >= 1 else ""
                    if kw and kw in title:
                        zones.append(title)

            # area가 없으면 우측 패널 span/td 에서 구역번호 파싱
            if not zones:
                for el in bs.find_all(["span", "td", "li"]):
                    t = el.get_text(strip=True)
                    if "영역" in t or "구역" in t:
                        zones.append(t)
        except:
            pass

        driver.switch_to.default_content()

        # 중복 제거 + 정렬
        seen = set()
        unique = []
        for z in zones:
            if z not in seen:
                seen.add(z)
                unique.append(z)
        return unique

    # ── 구역 선택 요청
    def _ask_zones(self, grade_idx):
        zone_list = self._get_zones(grade_idx)

        if not zone_list:
            self.log("구역 목록을 읽지 못했습니다. 직접 입력해주세요 (예: 001영역,002영역)")
        else:
            for i, z in enumerate(zone_list, start=1):
                self.log(f"{i}. {z}")

        self.log("→")

        answer = self._ask_user(timeout=120)
        if not answer:
            return zone_list  # 입력 없으면 전체

        self.log(f"→ {answer}")

        # 숫자 입력이면 번호로 선택, 아니면 문자 그대로 사용
        selected = []
        for part in answer.split(","):
            part = part.strip()
            try:
                idx = int(part) - 1
                if 0 <= idx < len(zone_list):
                    selected.append(zone_list[idx])
            except:
                if part:
                    selected.append(part)

        return selected if selected else zone_list

    # ── 구역 순회 + 좌석 선택
    def _rotate_zones(self, zone_names, grade_idx):
        GRADE_KW = ["스탠딩R","스탠딩S","지정석R","지정석S","지정석A","지정석B"]
        target_kw = GRADE_KW[grade_idx - 1] if grade_idx >= 1 else None

        self.log(f"구역 순회를 시작합니다 (딜레이 {self.delay}초)")

        driver = self.driver
        zone_cycle = 0

        while True:
            self._wait(0)  # 중단/일시정지 체크

            for zone_name in zone_names:
                self._wait(0)

                # ── 좌석 iframe 진입
                driver.switch_to.default_content()
                for fid in ["ifrmSeat", "mainFrame"]:
                    try:
                        driver.switch_to.frame(driver.find_element(By.ID, fid))
                        break
                    except:
                        pass

                # ── 구역 클릭
                clicked = False
                try:
                    areas = driver.find_elements(By.TAG_NAME, "area")
                    for area in areas:
                        title = area.get_attribute("title") or area.get_attribute("alt") or ""
                        if zone_name in title or title in zone_name:
                            driver.execute_script("arguments[0].click();", area)
                            clicked = True
                            break
                except:
                    pass

                if not clicked:
                    # href javascript 방식 시도
                    try:
                        areas = driver.find_elements(By.TAG_NAME, "area")
                        for area in areas:
                            href = area.get_attribute("href") or ""
                            if zone_name.replace("영역","").strip() in href:
                                driver.execute_script(
                                    href.replace("javascript:", "")
                                )
                                clicked = True
                                break
                    except:
                        pass

                self._wait(self.delay)

                # ── 퍼즐 슬라이더 감지 + 자동 해제
                self._solve_puzzle_if_present()

                # ── 좌석 탐색
                seat_found = self._try_select_seat(target_kw)
                if seat_found:
                    driver.switch_to.default_content()
                    return True

                driver.switch_to.default_content()

            zone_cycle += 1
            if zone_cycle % 5 == 0:
                self.log(f"구역 순회 {zone_cycle}바퀴 완료 - 계속 탐색 중...")

    # ── 현재 구역에서 좌석 클릭 시도
    def _try_select_seat(self, target_kw):
        driver = self.driver
        try:
            seats = driver.find_elements(
                By.CSS_SELECTOR, "img.stySeat, span[onclick*='Seat'], td[onclick*='Seat']"
            )
            for seat in seats:
                alt  = seat.get_attribute("alt")   or ""
                title= seat.get_attribute("title") or ""
                text = (alt + title).upper()

                if target_kw and target_kw.upper() not in text:
                    continue

                driver.execute_script("arguments[0].click();", seat)
                self.log(f"좌석 선택: {(alt or title)[:30]}")
                self._wait(0.3)
                return True
        except:
            pass
        return False

    # ── 퍼즐 슬라이더 감지 + 자동 해제
    def _solve_puzzle_if_present(self):
        driver = self.driver

        driver.switch_to.default_content()
        for fid in ["ifrmSeat", "mainFrame"]:
            try:
                driver.switch_to.frame(driver.find_element(By.ID, fid))
                break
            except:
                pass

        # 퍼즐 팝업 존재 여부 확인
        puzzle_present = False
        for sel in [".slider_wrap", ".puzzle_wrap", "[class*='slider']", "[class*='puzzle']"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    puzzle_present = True
                    break
            except:
                pass

        if not puzzle_present:
            # 텍스트로도 확인
            try:
                if "슬라이더를 밀어" in driver.page_source:
                    puzzle_present = True
            except:
                pass

        if not puzzle_present:
            driver.switch_to.default_content()
            return

        # 배경/조각 이미지 캡처
        bg_path    = "puzzle_bg.png"
        piece_path = "puzzle_piece.png"
        offset     = 140  # 기본값

        bg_el    = None
        piece_el = None
        for bg_sel in ["#captcha_bg", "#puzzle_bg", "img[id*='bg']", ".puzzle_bg", ".bg_img"]:
            try:
                bg_el = driver.find_element(By.CSS_SELECTOR, bg_sel)
                break
            except:
                pass
        for pc_sel in ["#captcha_piece", "#puzzle_piece", "img[id*='piece']", ".puzzle_piece"]:
            try:
                piece_el = driver.find_element(By.CSS_SELECTOR, pc_sel)
                break
            except:
                pass

        if bg_el and piece_el:
            try:
                bg_el.screenshot(bg_path)
                piece_el.screenshot(piece_path)
                offset = self._calc_puzzle_offset(bg_path, piece_path)
            except:
                pass

        self.sig.log_signal.emit(f"[퍼즐 감지 목표 위치: {offset}px]")

        # 슬라이더 드래그
        slider_el = None
        for sl_sel in [".btn_slide_right", ".slide_btn", ".slider_btn",
                       "div[class*='slider'] span", "#nc_1__scale_text"]:
            try:
                slider_el = driver.find_element(By.CSS_SELECTOR, sl_sel)
                break
            except:
                pass

        if slider_el:
            try:
                ac = ActionChains(driver)
                ac.click_and_hold(slider_el).pause(0.3)
                steps   = 20
                step_px = offset / steps
                for _ in range(steps):
                    ac.move_by_offset(step_px, 0).pause(0.02)
                ac.release().perform()
                self._wait(1.2)
            except Exception as e:
                self.sig.log_signal.emit(f"[슬라이더 드래그 오류: {e}]")

        driver.switch_to.default_content()

    def _calc_puzzle_offset(self, bg_path, piece_path):
        try:
            bg    = np.array(Image.open(bg_path).convert("L"), dtype=np.float32)
            piece = np.array(Image.open(piece_path).convert("L"), dtype=np.float32)
            ph, pw = piece.shape
            bh, bw = bg.shape
            best_x, best_score = 0, float("inf")
            for x in range(0, bw - pw, 2):
                score = float(np.mean(np.abs(bg[:ph, x:x+pw] - piece)))
                if score < best_score:
                    best_score = score
                    best_x = x
            return best_x
        except:
            return 140

    # ── 좌석선택완료 클릭
    def _click_seat_complete(self):
        driver = self.driver
        self.log("좌석선택완료 클릭")

        driver.switch_to.default_content()
        for fid in ["ifrmSeat", "mainFrame"]:
            try:
                driver.switch_to.frame(driver.find_element(By.ID, fid))
                break
            except:
                pass

        for fn in ["fnSelect()", "fnComplete()", "fnSelectSeat()"]:
            try:
                driver.execute_script(fn)
                self._wait(0.5)
                break
            except:
                pass

        # 버튼 직접 클릭 시도
        try:
            btn = driver.find_element(
                By.XPATH,
                "//a[contains(text(),'좌석선택완료')] | //button[contains(text(),'좌석선택완료')]"
            )
            driver.execute_script("arguments[0].click();", btn)
        except:
            pass

        driver.switch_to.default_content()
        self._wait(1.5)

    # ── 결제 대기 + 소리 알림
    def _wait_payment(self):
        driver = self.driver
        self.log("결제 대기 중 - 소리 알림 시작")

        # 소리 알림 (반복 재생)
        def _beep():
            for _ in range(10):
                try:
                    winsound.Beep(1000, 400)
                    time.sleep(0.15)
                    winsound.Beep(1300, 400)
                    time.sleep(0.3)
                except:
                    break
        threading.Thread(target=_beep, daemon=True).start()

        # 결제 완료 감지 (최대 30분)
        for _ in range(1800):
            self._wait(1)
            try:
                cur = driver.current_url
                if any(k in cur for k in ["payment", "pay", "order", "checkout", "BookEnd", "완료"]):
                    self.log("✅ 결제 완료!")
                    return
            except:
                pass

        self.log("결제 대기 시간 초과")

    # ── 좌석 등급 선택
    def _ask_seat_grade(self):
        GRADES = [
            "스탠딩R",
            "스탠딩S",
            "지정석R",
            "지정석S",
            "지정석A",
            "지정석B",
        ]
        self.log("좌석 등급을 입력해주세요:")
        self.log("1. 모두")
        for i, g in enumerate(GRADES, start=2):
            self.log(f"{i}. {g}")

        answer = self._ask_user(timeout=120)
        if answer is None:
            self.log("입력 시간 초과 - 모두로 진행")
            return 0
        try:
            sel = int(answer)
        except:
            sel = 1

        self.log(f"→ {answer}")

        if sel == 1:
            return 0              # 0 = 모두
        elif 2 <= sel <= len(GRADES) + 1:
            return sel - 2        # GRADES 인덱스
        else:
            return 0

    # ── 보안문자 처리
    def _handle_captcha(self):
        driver = self.driver
        wait   = WebDriverWait(driver, 8)

        for attempt in range(10):
            self._wait(0.3)
            driver.switch_to.default_content()

            # iframe 진입
            for fid in ["ifrmSeat", "ifrmCaptcha"]:
                try:
                    driver.switch_to.frame(driver.find_element(By.ID, fid))
                    break
                except:
                    pass

            # 캡차 이미지 확인
            captcha_el = None
            for sel in ["#imgCaptcha", "img[id*='captcha' i]"]:
                try:
                    captcha_el = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                    )
                    break
                except:
                    pass

            if captcha_el is None:
                driver.switch_to.default_content()
                return True  # 캡차 없음

            # 사용자에게 입력 요청
            self.log("보안 문자를 입력해주세요. 입력 후, 0을 입력해주세요 →")
            driver.switch_to.default_content()

            answer = self._ask_user(timeout=60)
            if not answer:
                self.log("보안문자 입력 시간 초과")
                return False

            self.log(f"→ {answer}")

            # iframe 재진입 후 입력
            for fid in ["ifrmSeat", "ifrmCaptcha"]:
                try:
                    driver.switch_to.frame(driver.find_element(By.ID, fid))
                    break
                except:
                    pass

            try:
                try:
                    driver.find_element(
                        By.XPATH, "//div[@class='validationTxt']//span"
                    ).click()
                except:
                    pass
                inp = driver.find_element(By.ID, "txtCaptcha")
                inp.clear()
                inp.send_keys(answer)
                self._wait(0.3)
                driver.execute_script("fnCheck();")
                self._wait(0.8)
            except Exception as e:
                self.log(f"보안문자 입력 오류: {e}")
                driver.switch_to.default_content()
                continue

            # 성공 여부 확인
            page = driver.page_source
            if 'validationTxt alert' in page or "다시 입력" in page:
                self.log(f"보안문자 오류 - 재시도 ({attempt+1}/10)")
                try:
                    driver.execute_script("fnCapchaRefresh();")
                except:
                    pass
                driver.switch_to.default_content()
                self._wait(0.5)
                continue
            else:
                self.log("→ 보안문자 통과")
                driver.switch_to.default_content()
                return True

        driver.switch_to.default_content()
        return False

    def run(self):
        try:
            self.log("매크로 실행 시작")
            self.log("로그인을 완료해 주세요.")

            # 로그인 완료 대기 (최대 5분)
            for _ in range(300):
                self._wait(1)
                try:
                    cur = self.driver.current_url
                    if "accounts" not in cur and "login" not in cur and "nol.interpark" in cur:
                        break
                except:
                    pass
            else:
                self.log("로그인 대기 시간 초과")
                return

            self.log("→ 로그인 완료")
            self.log("원하는 링크에 들어가서 [예매하기] 버튼을 눌러 주세요.")

            # 예매(Book) 페이지 진입 대기 (최대 30분)
            for _ in range(1800):
                self._wait(1)
                try:
                    cur = self.driver.current_url
                    if "poticket" in cur or "Book" in cur:
                        self.log("예매 페이지 감지")
                        break
                except:
                    pass

            self._wait(2)

            # 보안문자 처리
            self._handle_captcha()

            self._wait(0.5)

            # 좌석 등급 선택
            grade_idx = self._ask_seat_grade()   # 0=모두, 1~6=특정등급

            self._wait(0.3)

            # 구역 선택
            selected_zones = self._ask_zones(grade_idx)
            self.log(f"선택 구역: {', '.join(selected_zones) if selected_zones else '전체'}")

            self._wait(0.3)

            # 구역 순회 + 좌석 선택
            self._rotate_zones(selected_zones, grade_idx)

            # 좌석선택완료 클릭
            self._click_seat_complete()

            # 결제 대기 + 소리 알림
            self._wait_payment()

        except InterruptedError:
            self.log("매크로 중단됨")
        except Exception as e:
            self.log(f"오류: {e}\n{traceback.format_exc()}")


# ──────────────────────────────────────────────
#  컨트롤 창
# ──────────────────────────────────────────────
class ControlWindow(QWidget):
    def __init__(self, driver, login_type, user_id, user_pw, delay):
        super().__init__()
        self.setWindowTitle("인터파크티켓 취소표 매크로")
        self.setFont(QFont("맑은 고딕", 9))
        self.setFixedWidth(310)

        self._sig    = Signals()
        self._thread = MacroThread(driver, login_type, user_id, user_pw, delay, self._sig)
        self._paused = False

        self._sig.log_signal.connect(self._append_log)
        self._sig.captcha_signal.connect(self._show_captcha_input)
        self._sig.input_hide.connect(self._hide_captcha_input)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 로그창
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(130)
        self.log_box.setFont(QFont("맑은 고딕", 9))
        self.log_box.setStyleSheet(
            "background:#ffffff; color:#222; border:1px solid #ccc;"
        )
        layout.addWidget(self.log_box)

        # 보안문자 입력행 (평소엔 숨김)
        self.captcha_row = QWidget()
        cap_layout = QHBoxLayout()
        cap_layout.setContentsMargins(0, 0, 0, 0)
        cap_layout.setSpacing(4)
        self.captcha_edit = QLineEdit()
        self.captcha_edit.setPlaceholderText("보안문자 입력")
        self.captcha_edit.setFixedHeight(28)
        self.captcha_edit.returnPressed.connect(self._submit_captcha)
        self.captcha_btn = QPushButton("입력완료")
        self.captcha_btn.setFixedHeight(28)
        self.captcha_btn.setFixedWidth(64)
        self.captcha_btn.setStyleSheet(
            "background:#4a90d9; color:white; font-weight:bold; border-radius:3px;"
        )
        self.captcha_btn.clicked.connect(self._submit_captcha)
        cap_layout.addWidget(self.captcha_edit)
        cap_layout.addWidget(self.captcha_btn)
        self.captcha_row.setLayout(cap_layout)
        self.captcha_row.hide()
        layout.addWidget(self.captcha_row)

        # 중단하기 / 일시정지
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        self.btn_stop = QPushButton("중단하기")
        self.btn_stop.setFixedHeight(32)
        self.btn_stop.setStyleSheet(
            "background:#4a4a4a; color:white; font-weight:bold; border-radius:4px;"
        )
        self.btn_stop.clicked.connect(self._on_stop)

        self.btn_pause = QPushButton("일시정지")
        self.btn_pause.setFixedHeight(32)
        self.btn_pause.setStyleSheet(
            "background:#3db06e; color:white; font-weight:bold; border-radius:4px;"
        )
        self.btn_pause.clicked.connect(self._on_pause)

        btn_row.addWidget(self.btn_stop)
        btn_row.addWidget(self.btn_pause)
        layout.addLayout(btn_row)

        self.setLayout(layout)
        self.adjustSize()
        self._thread.start()

    def _append_log(self, msg):
        self.log_box.append(msg)
        self.log_box.moveCursor(QTextCursor.End)

    def _show_captcha_input(self):
        self.captcha_edit.clear()
        self.captcha_row.show()
        self.captcha_edit.setFocus()
        self.adjustSize()

    def _hide_captcha_input(self):
        self.captcha_row.hide()
        self.adjustSize()

    def _submit_captcha(self):
        text = self.captcha_edit.text().strip()
        self._thread.set_captcha_answer(text)

    def _on_stop(self):
        self._thread.stop()
        self.btn_stop.setEnabled(False)
        self.btn_pause.setEnabled(False)

    def _on_pause(self):
        self._paused = self._thread.pause()
        if self._paused:
            self.btn_pause.setText("재  개")
            self.btn_pause.setStyleSheet(
                "background:#d0a020; color:white; font-weight:bold; border-radius:4px;"
            )
        else:
            self.btn_pause.setText("일시정지")
            self.btn_pause.setStyleSheet(
                "background:#3db06e; color:white; font-weight:bold; border-radius:4px;"
            )

    def closeEvent(self, event):
        self._thread.stop()
        self._thread.wait(2000)
        event.accept()


# ──────────────────────────────────────────────
#  로그인 설정 창
# ──────────────────────────────────────────────
class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("인터파크티켓 취소표 매크로")
        self.setFixedWidth(300)
        self.setFont(QFont("맑은 고딕", 10))

        self._control_win = None

        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(16, 16, 16, 16)

        # 로그인 탭
        lbl_login = QLabel("로그인")
        lbl_login.setFont(QFont("맑은 고딕", 9))
        layout.addWidget(lbl_login)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        self.btn_interpark = QPushButton("인터파크")
        self.btn_kakao     = QPushButton("카카오")
        self.btn_naver     = QPushButton("네이버")

        self._tab_group   = QButtonGroup(self)
        self._tab_buttons = [self.btn_interpark, self.btn_kakao, self.btn_naver]
        for i, btn in enumerate(self._tab_buttons):
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            self._tab_group.addButton(btn, i)
            tab_row.addWidget(btn)

        self.btn_interpark.setChecked(True)
        self._tab_group.buttonClicked.connect(lambda _: self._apply_tab_style())
        self._apply_tab_style()
        layout.addLayout(tab_row)

        # ID / PW
        row_id = QHBoxLayout()
        lbl_id = QLabel("ID")
        lbl_id.setFixedWidth(40)
        self.edit_id = QLineEdit()
        self.edit_id.setFixedHeight(28)
        row_id.addWidget(lbl_id)
        row_id.addWidget(self.edit_id)
        layout.addLayout(row_id)

        row_pw = QHBoxLayout()
        lbl_pw = QLabel("PW")
        lbl_pw.setFixedWidth(40)
        self.edit_pw = QLineEdit()
        self.edit_pw.setEchoMode(QLineEdit.Password)
        self.edit_pw.setFixedHeight(28)
        row_pw.addWidget(lbl_pw)
        row_pw.addWidget(self.edit_pw)
        layout.addLayout(row_pw)

        # 딜레이
        row_delay = QHBoxLayout()
        lbl_delay = QLabel("딜레이")
        lbl_delay.setFixedWidth(40)
        self.spin_delay = QSpinBox()
        self.spin_delay.setRange(1, 60)
        self.spin_delay.setValue(1)
        self.spin_delay.setFixedHeight(28)
        row_delay.addWidget(lbl_delay)
        row_delay.addWidget(self.spin_delay)
        row_delay.addStretch()
        layout.addLayout(row_delay)

        # 유효기간
        lbl_expire = QLabel(f"유효기간: {EXPIRE_DATE}")
        lbl_expire.setAlignment(Qt.AlignRight)
        lbl_expire.setStyleSheet("color:#888; font-size:9px;")
        layout.addWidget(lbl_expire)

        # 시작하기
        self.btn_start = QPushButton("시작하기")
        self.btn_start.setFixedHeight(36)
        self.btn_start.setStyleSheet(
            "background:#3c3c3c; color:white; font-weight:bold; font-size:12px; border-radius:4px;"
        )
        self.btn_start.clicked.connect(self._on_start)
        layout.addWidget(self.btn_start)

        self.setLayout(layout)

    def _apply_tab_style(self):
        for btn in self._tab_buttons:
            if btn.isChecked():
                btn.setStyleSheet(
                    "background:#4a90d9; color:white; font-weight:bold; border:none; border-radius:3px;"
                )
            else:
                btn.setStyleSheet(
                    "background:#e0e0e0; color:#333; border:none; border-radius:3px;"
                )

    def _on_start(self):
        login_type = ["interpark", "kakao", "naver"][self._tab_group.checkedId()]
        user_id    = self.edit_id.text().strip()
        user_pw    = self.edit_pw.text()
        delay      = self.spin_delay.value()

        try:
            options = webdriver.ChromeOptions()
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option("useAutomationExtension", False)
            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=options
            )
            driver.set_page_load_timeout(30)
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"}
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"Chrome 드라이버 실행 실패:\n{e}")
            return

        try:
            driver.get("https://accounts.yanolja.com/?clientId=inpark-pc&postProc=FULLSCREEN&origin=https%3A%2F%2Fnol.interpark.com")
        except:
            pass

        self._control_win = ControlWindow(driver, login_type, user_id, user_pw, delay)
        self._control_win.show()
        self.hide()


# ──────────────────────────────────────────────
#  진입점
# ──────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("맑은 고딕", 10))
    win = LoginWindow()
    win.show()
    sys.exit(app.exec_())
