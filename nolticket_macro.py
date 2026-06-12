# -*- encoding:utf8 -*-
"""
놀티켓 취소표 자동예매 매크로
- 로그인은 사용자가 직접 진행
- 보안문자(캡차)부터 자동 처리 시작
- 구역 순회(zone rotation)로 좌석 탐색
- 퍼즐 슬라이더 자동 풀이
"""

import sys
import os
import time
import traceback
import re
import threading

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from urllib.request import urlretrieve
from PIL import Image, ImageFilter
import numpy as np

from PyQt5.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt5.QtGui import QFont, QPixmap, QTextCursor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QDialog, QLineEdit,
    QGroupBox, QFormLayout, QSpinBox, QCheckBox, QMessageBox,
    QDoubleSpinBox
)


# ─────────────────────────────────────────────────────────
#  등급 키워드
# ─────────────────────────────────────────────────────────
GRADE_KEYWORDS = [
    ["스탠딩R", "스탠딩 R", "STANDING R"],
    ["스탠딩S", "스탠딩 S", "STANDING S"],
    ["지정석R", "지정석 R"],
    ["지정석S", "지정석 S"],
    ["지정석A", "지정석 A"],
    ["지정석B", "지정석 B"],
]


# ─────────────────────────────────────────────────────────
#  캡차 입력 다이얼로그
# ─────────────────────────────────────────────────────────
class CaptchaDialog(QDialog):
    def __init__(self, img_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("보안문자 입력")
        self.setFont(QFont("맑은 고딕", 11))
        self.setFixedWidth(340)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout()

        # 캡차 이미지
        lbl_img = QLabel()
        lbl_img.setAlignment(Qt.AlignCenter)
        if os.path.exists(img_path):
            lbl_img.setPixmap(QPixmap(img_path).scaledToWidth(300))
        else:
            lbl_img.setText("이미지 없음")
        layout.addWidget(lbl_img)

        # 입력창
        self.edit = QLineEdit()
        self.edit.setFont(QFont("Consolas", 20))
        self.edit.setAlignment(Qt.AlignCenter)
        self.edit.setPlaceholderText("문자를 입력하세요")
        self.edit.returnPressed.connect(self.accept)
        layout.addWidget(self.edit)

        # 확인 버튼
        btn = QPushButton("입력 완료")
        btn.setFixedHeight(38)
        btn.setStyleSheet("background:#2c3e50; color:white; font-weight:bold; font-size:13px;")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)

        self.setLayout(layout)

    def get_text(self):
        return self.edit.text().strip()


# ─────────────────────────────────────────────────────────
#  신호 브릿지 (스레드 → GUI)
# ─────────────────────────────────────────────────────────
class Signals(QObject):
    log_signal       = pyqtSignal(str)          # 로그 메시지
    captcha_signal   = pyqtSignal(str)          # 캡차 이미지 경로 → 다이얼로그 표시
    success_signal   = pyqtSignal(str)          # 예매 성공 메시지
    error_signal     = pyqtSignal(str)          # 오류 메시지


# ─────────────────────────────────────────────────────────
#  매크로 작업 스레드
# ─────────────────────────────────────────────────────────
class MacroThread(QThread):
    def __init__(self, driver, count, grade_check, signals):
        super().__init__()
        self.driver      = driver
        self.count       = count
        self.grade_check = grade_check
        self.sig         = signals

        self._stop  = False
        self._pause = False

        # 캡차 응답을 스레드에 전달하기 위한 이벤트/변수
        self._captcha_event  = threading.Event()
        self._captcha_answer = ""

    # ── 외부 제어
    def stop(self):
        self._stop = True

    def pause(self):
        self._pause = not self._pause
        return self._pause

    # 캡차 답 수신 (GUI 스레드에서 호출)
    def set_captcha_answer(self, text):
        self._captcha_answer = text
        self._captcha_event.set()

    # ── 유틸
    def log(self, msg):
        now = time.strftime("%H:%M:%S")
        self.sig.log_signal.emit(f"[{now}] {msg}")

    def _wait_or_stop(self, sec=0.5):
        """중단/일시정지 처리하며 대기"""
        deadline = time.time() + sec
        while time.time() < deadline:
            if self._stop:
                raise InterruptedError("사용자 중단")
            while self._pause:
                time.sleep(0.1)
                if self._stop:
                    raise InterruptedError("사용자 중단")
            time.sleep(0.05)

    # ── 이미지 전처리 (캡차 선명화)
    def _clean_image(self, path):
        try:
            img = Image.open(path).convert("L")
            img = img.point(lambda x: 0 if x < 160 else 255)
            img.save(path)
        except:
            pass

    # ─────────────────────────────────
    #  캡차 처리
    # ─────────────────────────────────
    def _handle_captcha(self):
        self.log("보안문자 처리 시작")
        driver = self.driver
        wait = WebDriverWait(driver, 10)

        for attempt in range(10):
            self._wait_or_stop()

            # iframe 진입 시도
            driver.switch_to.default_content()
            for frame_id in ["ifrmSeat", "ifrmCaptcha", "captchaFrame"]:
                try:
                    driver.switch_to.frame(driver.find_element(By.ID, frame_id))
                    break
                except:
                    pass

            # 캡차 이미지 찾기
            captcha_img_el = None
            for sel in ["#imgCaptcha", "img[id*='captcha' i]", "img[src*='captcha' i]"]:
                try:
                    captcha_img_el = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, sel)))
                    break
                except:
                    pass

            if captcha_img_el is None:
                self.log("캡차 이미지 없음 - 건너뜀")
                driver.switch_to.default_content()
                return True

            # 이미지 저장
            img_src = captcha_img_el.get_attribute("src") or ""
            img_path = os.path.abspath("captcha.jpg")
            try:
                if img_src.startswith("http"):
                    urlretrieve(img_src, img_path)
                else:
                    captcha_img_el.screenshot(img_path)
                self._clean_image(img_path)
            except Exception as e:
                self.log(f"캡차 이미지 저장 실패: {e}")

            # GUI 스레드에 캡차 다이얼로그 요청
            self._captcha_event.clear()
            self.sig.captcha_signal.emit(img_path)

            # 최대 60초 대기
            if not self._captcha_event.wait(timeout=60):
                self.log("캡차 입력 시간 초과")
                driver.switch_to.default_content()
                return False

            answer = self._captcha_answer
            if not answer:
                driver.switch_to.default_content()
                return False

            # 캡차 입력 & 검증
            try:
                # 텍스트 클릭 → 초기화
                try:
                    driver.find_element(By.XPATH, "//div[@class='validationTxt']//span").click()
                except:
                    pass

                inp = driver.find_element(By.ID, "txtCaptcha")
                inp.clear()
                inp.send_keys(answer)
                self._wait_or_stop(0.3)

                driver.execute_script("fnCheck();")
                self._wait_or_stop(0.8)

            except Exception as e:
                self.log(f"캡차 입력 오류: {e}")
                driver.switch_to.default_content()
                continue

            # 성공 여부 확인
            try:
                page = driver.page_source
                if 'class="validationTxt alert"' in page or "올바른 문자" in page or "다시 입력" in page:
                    self.log(f"캡차 오류 - 재시도 ({attempt+1}/10)")
                    try:
                        driver.execute_script("fnCapchaRefresh();")
                    except:
                        pass
                    self._wait_or_stop(0.5)
                    continue
                else:
                    self.log("보안문자 통과")
                    driver.switch_to.default_content()
                    return True
            except:
                pass

            driver.switch_to.default_content()
            return True

        driver.switch_to.default_content()
        return False

    # ─────────────────────────────────
    #  구역 순회 좌석 선택
    # ─────────────────────────────────
    def _select_seat(self):
        self.log("좌석 선택 시작 (구역 순회)")
        driver = self.driver

        driver.switch_to.default_content()
        for frame_id in ["ifrmSeat", "mainFrame"]:
            try:
                driver.switch_to.frame(driver.find_element(By.ID, frame_id))
                break
            except:
                pass

        # 구역 목록 수집
        zone_elements = []
        try:
            zone_elements = driver.find_elements(By.XPATH, "//area | //map//area")
        except:
            pass
        if not zone_elements:
            try:
                zone_elements = driver.find_elements(By.CSS_SELECTOR, ".zoneArea, .zone-item, [id^='zone']")
            except:
                pass

        zone_count = len(zone_elements)
        self.log(f"구역 {zone_count}개 발견")

        for zone_idx in range(max(zone_count, 1)):
            self._wait_or_stop()

            # 구역 클릭
            if zone_count > 0:
                try:
                    zones = driver.find_elements(By.XPATH, "//area | //map//area")
                    if zone_idx < len(zones):
                        z = zones[zone_idx]
                        zone_name = z.get_attribute("title") or z.get_attribute("alt") or f"구역{zone_idx+1}"
                        self.log(f"구역 진입: {zone_name} ({zone_idx+1}/{zone_count})")
                        try:
                            href = z.get_attribute("href") or ""
                            if href and "javascript:" in href:
                                driver.execute_script(href.replace("javascript:", ""))
                            else:
                                driver.execute_script("arguments[0].click();", z)
                        except:
                            pass
                        self._wait_or_stop(0.8)
                except Exception as e:
                    self.log(f"구역 클릭 오류: {e}")

            # 좌석 탐색
            seat_found = self._try_click_seat()
            if seat_found:
                return True

        # 구역 진입 없이 직접 좌석 탐색
        if zone_count == 0:
            return self._try_click_seat()

        self.log("사용 가능한 좌석 없음")
        driver.switch_to.default_content()
        return False

    def _try_click_seat(self):
        """현재 좌석 맵에서 원하는 등급의 좌석 클릭. 성공 시 True"""
        driver = self.driver

        for sel in ["img.stySeat", "img[onclick*='seat']", "span[class*='seat']", "td[class*='seat']"]:
            try:
                seats = driver.find_elements(By.CSS_SELECTOR, sel)
                for seat_el in seats:
                    seat_text = (
                        seat_el.get_attribute("alt") or
                        seat_el.get_attribute("title") or
                        seat_el.get_attribute("class") or ""
                    ).upper()

                    for idx, flag in enumerate(self.grade_check):
                        if not flag:
                            continue
                        for kw in GRADE_KEYWORDS[idx]:
                            if kw.upper() in seat_text:
                                try:
                                    driver.execute_script("arguments[0].click();", seat_el)
                                    self.log(f"좌석 선택: {seat_text[:40]}")
                                    self._wait_or_stop(0.3)
                                    driver.switch_to.default_content()
                                    return True
                                except:
                                    pass
            except:
                pass
        return False

    # ─────────────────────────────────
    #  퍼즐 슬라이더 자동 풀이
    # ─────────────────────────────────
    def _solve_puzzle_slider(self):
        self.log("퍼즐 슬라이더 감지 - 자동 풀이 시도")
        driver = self.driver

        # 슬라이더 iframe 진입
        driver.switch_to.default_content()
        for frame_id in ["ifrmPuzzle", "sliderFrame", "secureFrame"]:
            try:
                driver.switch_to.frame(driver.find_element(By.ID, frame_id))
                break
            except:
                pass

        try:
            # 배경 이미지와 퍼즐 조각 이미지 찾기
            bg_el     = None
            piece_el  = None

            for bg_sel in ["#captcha_bg", "#bg_img", "img[id*='bg']", ".puzzle-bg", "canvas#bg"]:
                try:
                    bg_el = driver.find_element(By.CSS_SELECTOR, bg_sel)
                    break
                except:
                    pass

            for pc_sel in ["#captcha_piece", "#piece_img", "img[id*='piece']", ".puzzle-piece"]:
                try:
                    piece_el = driver.find_element(By.CSS_SELECTOR, pc_sel)
                    break
                except:
                    pass

            if bg_el is None or piece_el is None:
                # 슬라이더 바만 있는 경우
                self.log("슬라이더 이미지 탐색 실패 - 슬라이더 버튼 드래그 시도")
                self._drag_slider_blind()
                return

            # 스크린샷 촬영
            bg_path    = "puzzle_bg.png"
            piece_path = "puzzle_piece.png"
            bg_el.screenshot(bg_path)
            piece_el.screenshot(piece_path)

            # 퍼즐 조각 위치 계산
            offset = self._calc_puzzle_offset(bg_path, piece_path)
            self.log(f"퍼즐 위치: {offset}px")

            # 슬라이더 드래그
            slider_el = None
            for sl_sel in ["#nc_1__scale_text", ".btn_slide_right", ".slide-btn",
                           "div[class*='slider']", "span[class*='slider']"]:
                try:
                    slider_el = driver.find_element(By.CSS_SELECTOR, sl_sel)
                    break
                except:
                    pass

            if slider_el:
                ac = ActionChains(driver)
                ac.click_and_hold(slider_el).pause(0.3)
                # 천천히 이동 (anti-bot)
                steps = 20
                step_px = offset / steps
                for i in range(steps):
                    ac.move_by_offset(step_px, 0).pause(0.02)
                ac.release().perform()
                self.log("슬라이더 드래그 완료")
                self._wait_or_stop(1.5)
            else:
                self.log("슬라이더 버튼 없음 - 블라인드 드래그 시도")
                self._drag_slider_blind()

        except Exception as e:
            self.log(f"퍼즐 슬라이더 풀이 오류: {e}")
        finally:
            driver.switch_to.default_content()

    def _calc_puzzle_offset(self, bg_path, piece_path):
        """배경과 조각 이미지 비교로 X 오프셋 계산"""
        try:
            bg    = np.array(Image.open(bg_path).convert("L"), dtype=np.float32)
            piece = np.array(Image.open(piece_path).convert("L"), dtype=np.float32)

            ph, pw = piece.shape
            bh, bw = bg.shape

            best_x, best_score = 0, float("inf")
            for x in range(0, bw - pw, 2):
                region = bg[:ph, x:x+pw]
                score  = float(np.mean(np.abs(region - piece)))
                if score < best_score:
                    best_score = score
                    best_x = x

            return best_x
        except:
            return 140  # 기본값

    def _drag_slider_blind(self):
        """이미지 분석 없이 슬라이더를 끝까지 드래그"""
        driver = self.driver
        for sl_sel in [".btn_slide_right", ".slide-btn", "div[class*='slider']",
                       "#nc_1__scale_text", "span[class*='drag']"]:
            try:
                el = driver.find_element(By.CSS_SELECTOR, sl_sel)
                w  = el.size.get("width", 280)
                ac = ActionChains(driver)
                ac.click_and_hold(el).pause(0.3)
                steps = 20
                for _ in range(steps):
                    ac.move_by_offset(w / steps, 0).pause(0.03)
                ac.release().perform()
                self.log(f"블라인드 슬라이더 드래그 완료 ({w}px)")
                return
            except:
                pass

    # ─────────────────────────────────
    #  좌석선택완료 → 가격선택 → 다음단계
    # ─────────────────────────────────
    def _complete_booking(self):
        self.log("좌석선택완료 클릭")
        driver = self.driver

        # iframe 진입
        driver.switch_to.default_content()
        for frame_id in ["ifrmSeat", "mainFrame"]:
            try:
                driver.switch_to.frame(driver.find_element(By.ID, frame_id))
                break
            except:
                pass

        # 좌석선택완료
        for fn in ["fnSelect()", "fnComplete()", "fnSelectSeat()"]:
            try:
                driver.execute_script(fn)
                self._wait_or_stop(0.5)
                break
            except:
                pass

        driver.switch_to.default_content()
        self._wait_or_stop(1)

        # 가격/할인 iframe
        for frame_id in ["ifrmBookStep", "ifrmStep2", "mainFrame"]:
            try:
                driver.switch_to.frame(driver.find_element(By.ID, frame_id))
                break
            except:
                pass

        # 가격 선택 (첫번째 옵션)
        try:
            selects = driver.find_elements(By.XPATH, "//select")
            for sel_el in selects:
                try:
                    opts = sel_el.find_elements(By.TAG_NAME, "option")
                    for opt in opts:
                        if opt.get_attribute("value") not in ("", "0", "-1"):
                            driver.execute_script("arguments[0].selected=true;", opt)
                            driver.execute_script(
                                "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
                                sel_el
                            )
                            break
                except:
                    pass
        except:
            pass

        # 다음 단계
        for fn in ["fnNextStep('P')", "fnNext()", "fnStep2()"]:
            try:
                driver.execute_script(fn)
                self._wait_or_stop(0.5)
                break
            except:
                pass

        driver.switch_to.default_content()

    # ─────────────────────────────────
    #  메인 실행 흐름
    # ─────────────────────────────────
    def run(self):
        try:
            self.log("매크로 시작 - 브라우저에서 인터파크 예매 페이지를 열어주세요")
            self.log("로그인 후 예매 버튼을 클릭하면 자동으로 진행됩니다")

            driver = self.driver

            # 인터파크 예매 페이지 대기
            self.log("인터파크 예매 페이지 감지 대기 중...")
            for _ in range(600):  # 최대 10분 대기
                self._wait_or_stop(1)
                try:
                    cur = driver.current_url
                    if "interpark" in cur or "poticket" in cur or "ticket.interpark" in cur:
                        self.log(f"인터파크 예매 페이지 감지: {cur}")
                        break
                except:
                    pass
            else:
                self.log("페이지 감지 시간 초과 - 현재 페이지에서 진행합니다")

            self._wait_or_stop(2)

            # 보안문자(캡차) 처리
            captcha_ok = self._handle_captcha()
            if not captcha_ok:
                self.log("보안문자 처리 실패")

            self._wait_or_stop(1)

            # 퍼즐 슬라이더 있으면 처리
            try:
                cur_src = driver.page_source
                if "슬라이더를 밀어" in cur_src or "puzzle" in cur_src.lower() or "slider" in cur_src.lower():
                    self._solve_puzzle_slider()
                    self._wait_or_stop(1)
            except:
                pass

            # 좌석 선택
            seat_ok = self._select_seat()
            if not seat_ok:
                self.log("좌석을 선택하지 못했습니다 - 수동으로 진행하세요")
            else:
                self._wait_or_stop(0.5)

                # 퍼즐 슬라이더 2차 (좌석 선택 후 나타나는 경우)
                try:
                    cur_src = driver.page_source
                    if "슬라이더를 밀어" in cur_src or "puzzle" in cur_src.lower():
                        self._solve_puzzle_slider()
                        self._wait_or_stop(1)
                except:
                    pass

                # 좌석선택완료 → 가격선택
                self._complete_booking()

                # 결과 확인
                self._wait_or_stop(1.5)
                try:
                    cur = driver.current_url
                    if any(k in cur for k in ["payment", "pay", "order", "checkout", "BookEnd"]):
                        self.log("✅ 예매 성공! 결제 페이지 도달")
                        self.sig.success_signal.emit("✅ 취소표 예매 성공!\n브라우저에서 결제를 완료해 주세요.")
                    else:
                        self.log(f"현재 URL: {cur}")
                        self.log("결제 페이지로 이동하지 않았습니다. 브라우저를 확인해 주세요.")
                except:
                    pass

        except InterruptedError:
            self.log("매크로 중단됨")
        except Exception as e:
            self.log(f"오류: {e}\n{traceback.format_exc()}")
            self.sig.error_signal.emit(str(e))


# ─────────────────────────────────────────────────────────
#  설정 창 (시작 전)
# ─────────────────────────────────────────────────────────
class SettingsWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("놀티켓 취소표 자동예매 - 설정")
        self.setFont(QFont("맑은 고딕", 10))
        self.setFixedWidth(440)

        self.result = None  # 시작 버튼 누르면 설정값 저장

        layout = QVBoxLayout()

        # ── 안내
        grp_notice = QGroupBox("안내")
        g0 = QVBoxLayout()
        lbl = QLabel(
            "1. 아래 설정 후 [예매 시작] 클릭\n"
            "2. 열리는 브라우저에서 직접 로그인\n"
            "3. 놀티켓에서 예매하기 버튼 클릭\n"
            "4. 이후 보안문자·좌석선택·슬라이더 자동 처리"
        )
        lbl.setStyleSheet("color:#444; font-size:10px; line-height:1.6;")
        g0.addWidget(lbl)
        grp_notice.setLayout(g0)
        layout.addWidget(grp_notice)

        # ── 좌석 등급
        grp_seat = QGroupBox("좌석 등급 (복수 선택 가능)")
        gs = QVBoxLayout()

        self.cb_all = QCheckBox("전체 등급")
        self.cb_all.stateChanged.connect(self._toggle_all)
        gs.addWidget(self.cb_all)

        row1 = QHBoxLayout()
        lbl1 = QLabel("스탠딩")
        lbl1.setFixedWidth(48)
        self.cb_sr = QCheckBox("R  (165,000원)")
        self.cb_ss = QCheckBox("S  (154,000원)")
        row1.addWidget(lbl1); row1.addWidget(self.cb_sr); row1.addWidget(self.cb_ss)
        row1.addStretch()
        gs.addLayout(row1)

        row2 = QHBoxLayout()
        lbl2 = QLabel("지정석")
        lbl2.setFixedWidth(48)
        self.cb_jr = QCheckBox("R  (165,000원)")
        self.cb_js = QCheckBox("S  (154,000원)")
        self.cb_ja = QCheckBox("A  (143,000원)")
        self.cb_jb = QCheckBox("B  (132,000원)")
        row2.addWidget(lbl2)
        row2.addWidget(self.cb_jr); row2.addWidget(self.cb_js)
        row2.addWidget(self.cb_ja); row2.addWidget(self.cb_jb)
        row2.addStretch()
        gs.addLayout(row2)

        grp_seat.setLayout(gs)
        layout.addWidget(grp_seat)

        # ── 옵션
        grp_opt = QGroupBox("옵션")
        go = QFormLayout()
        self.spin_count = QSpinBox()
        self.spin_count.setRange(1, 4)
        self.spin_count.setValue(1)
        go.addRow("예매 매수", self.spin_count)
        grp_opt.setLayout(go)
        layout.addWidget(grp_opt)

        # ── 시작 버튼
        btn = QPushButton("▶  예매 시작")
        btn.setFixedHeight(42)
        btn.setStyleSheet("background:#c0392b; color:white; font-weight:bold; font-size:13px;")
        btn.clicked.connect(self._on_start)
        layout.addWidget(btn)

        self.setLayout(layout)

    def _toggle_all(self, state):
        checked = (state == Qt.Checked)
        for cb in [self.cb_sr, self.cb_ss, self.cb_jr, self.cb_js, self.cb_ja, self.cb_jb]:
            cb.setChecked(checked)

    def _on_start(self):
        grade_check = [
            self.cb_sr.isChecked(),
            self.cb_ss.isChecked(),
            self.cb_jr.isChecked(),
            self.cb_js.isChecked(),
            self.cb_ja.isChecked(),
            self.cb_jb.isChecked(),
        ]
        if not any(grade_check):
            QMessageBox.warning(self, "오류", "좌석 등급을 하나 이상 선택하세요.")
            return
        self.result = {
            "count":       self.spin_count.value(),
            "grade_check": grade_check,
        }
        self.close()


# ─────────────────────────────────────────────────────────
#  메인 컨트롤 창 (매크로 실행 중)
# ─────────────────────────────────────────────────────────
class MainWindow(QWidget):
    def __init__(self, driver, count, grade_check):
        super().__init__()
        self.setWindowTitle("놀티켓 취소표 자동예매")
        self.setFont(QFont("맑은 고딕", 10))
        self.setMinimumSize(420, 320)

        self._driver = driver
        self._sig    = Signals()
        self._thread = MacroThread(driver, count, grade_check, self._sig)

        self._is_paused = False

        # 신호 연결
        self._sig.log_signal.connect(self._append_log)
        self._sig.captcha_signal.connect(self._show_captcha_dialog)
        self._sig.success_signal.connect(self._on_success)
        self._sig.error_signal.connect(self._on_error)

        # ── 레이아웃
        vbox = QVBoxLayout()

        lbl_title = QLabel("놀티켓 취소표 자동예매")
        lbl_title.setFont(QFont("맑은 고딕", 13, QFont.Bold))
        lbl_title.setAlignment(Qt.AlignCenter)
        vbox.addWidget(lbl_title)

        # 로그창
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Consolas", 9))
        self.log_box.setStyleSheet("background:#1e1e1e; color:#d4d4d4;")
        vbox.addWidget(self.log_box)

        # 버튼
        btn_row = QHBoxLayout()

        self.btn_pause = QPushButton("⏸  일시정지")
        self.btn_pause.setFixedHeight(36)
        self.btn_pause.setStyleSheet("background:#2980b9; color:white; font-weight:bold;")
        self.btn_pause.clicked.connect(self._toggle_pause)
        btn_row.addWidget(self.btn_pause)

        self.btn_stop = QPushButton("⏹  중단하기")
        self.btn_stop.setFixedHeight(36)
        self.btn_stop.setStyleSheet("background:#c0392b; color:white; font-weight:bold;")
        self.btn_stop.clicked.connect(self._stop_macro)
        btn_row.addWidget(self.btn_stop)

        vbox.addLayout(btn_row)
        self.setLayout(vbox)

        # 매크로 시작
        self._thread.start()

    def _append_log(self, msg):
        self.log_box.append(msg)
        self.log_box.moveCursor(QTextCursor.End)
        # 로그 파일에도 기록
        try:
            with open("nolticket_log.txt", "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except:
            pass

    def _show_captcha_dialog(self, img_path):
        dlg = CaptchaDialog(img_path, self)
        dlg.exec_()
        answer = dlg.get_text()
        self._thread.set_captcha_answer(answer)

    def _toggle_pause(self):
        self._is_paused = self._thread.pause()
        if self._is_paused:
            self.btn_pause.setText("▶  재개하기")
            self.btn_pause.setStyleSheet("background:#27ae60; color:white; font-weight:bold;")
            self._append_log("[--:--:--] 일시정지")
        else:
            self.btn_pause.setText("⏸  일시정지")
            self.btn_pause.setStyleSheet("background:#2980b9; color:white; font-weight:bold;")
            self._append_log("[--:--:--] 재개")

    def _stop_macro(self):
        self._thread.stop()
        self._append_log("[--:--:--] 중단 요청됨")
        self.btn_stop.setEnabled(False)
        self.btn_pause.setEnabled(False)

    def _on_success(self, msg):
        QMessageBox.information(self, "예매 성공! 🎉", msg)

    def _on_error(self, msg):
        QMessageBox.critical(self, "오류 발생", msg)

    def closeEvent(self, event):
        self._thread.stop()
        self._thread.wait(2000)
        event.accept()


# ─────────────────────────────────────────────────────────
#  Selenium 드라이버 생성
# ─────────────────────────────────────────────────────────
def make_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"}
    )
    return driver


# ─────────────────────────────────────────────────────────
#  진입점
# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("맑은 고딕", 10))

    # 1) 설정 창
    settings_win = SettingsWindow()
    settings_win.show()
    app.exec_()

    if settings_win.result is None:
        sys.exit()

    cfg = settings_win.result

    # 2) 브라우저 열기
    try:
        driver = make_driver()
        driver.get("https://www.nolticket.com")
    except Exception as e:
        QMessageBox.critical(None, "드라이버 오류", f"Chrome 드라이버 실행 실패:\n{e}")
        sys.exit(1)

    # 3) 메인 컨트롤 창 (매크로 실행)
    main_win = MainWindow(driver, cfg["count"], cfg["grade_check"])
    main_win.show()

    ret = app.exec_()

    try:
        driver.quit()
    except:
        pass

    sys.exit(ret)
