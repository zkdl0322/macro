# -*- coding: utf-8 -*-

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
from selenium.webdriver.common.action_chains import ActionChains
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from PIL import Image
import numpy as np

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QSpinBox, QPushButton,
    QButtonGroup, QTextEdit, QMessageBox
)

EXPIRE_DATE = "~26.09.30"
LOGIN_URL   = (
    "https://accounts.yanolja.com/"
    "?clientId=inpark-pc&postProc=FULLSCREEN"
    "&origin=https%3A%2F%2Fnol.interpark.com"
)
GRADES = ["스탠딩R", "스탠딩S", "지정석R", "지정석S", "지정석A", "지정석B"]


# ───────────────────────────────────────────────
#  신호 브릿지
# ───────────────────────────────────────────────
class Signals(QObject):
    log_signal     = Signal(str)
    captcha_signal = Signal()
    input_hide     = Signal()


# ───────────────────────────────────────────────
#  매크로 스레드
# ───────────────────────────────────────────────
class MacroThread(QThread):

    def __init__(self, driver, delay, signals):
        super().__init__()
        self.driver  = driver
        self.delay   = delay
        self.sig     = signals
        self._stop   = False
        self._pause  = False
        self._ev     = threading.Event()
        self._answer = ""

    # ── 제어 ──────────────────────────────────
    def stop(self):
        self._stop = True

    def toggle_pause(self):
        self._pause = not self._pause
        return self._pause

    def set_answer(self, text):
        self._answer = text
        self._ev.set()

    # ── 유틸 ──────────────────────────────────
    def log(self, msg):
        ts = time.strftime("%Y/%m/%d %H:%M:%S")
        self.sig.log_signal.emit(f"[{ts}] {msg}")

    def _wait(self, sec):
        end = time.time() + sec
        while time.time() < end:
            if self._stop:
                raise InterruptedError
            while self._pause:
                time.sleep(0.1)
                if self._stop:
                    raise InterruptedError
            time.sleep(0.05)

    def _ask(self, timeout=120):
        """GUI 입력창을 띄우고 사용자 입력을 기다린다."""
        self._ev.clear()
        self.sig.captcha_signal.emit()
        ok = self._ev.wait(timeout=timeout)
        ans = self._answer
        self.sig.input_hide.emit()
        return ans if ok else None

    def _cur_url(self):
        try:
            return self.driver.current_url
        except Exception:
            return ""

    def _page_src(self):
        try:
            return self.driver.page_source
        except Exception:
            return ""

    def _switch_frame(self, *ids):
        """지정한 id 목록 중 첫 번째로 찾은 iframe으로 전환."""
        self.driver.switch_to.default_content()
        for fid in ids:
            try:
                self.driver.switch_to.frame(
                    self.driver.find_element(By.ID, fid)
                )
                return True
            except Exception:
                pass
        return False

    # ── 로그인 감지 ────────────────────────────
    def _is_logged_in(self):
        cur = self._cur_url()
        return (
            "login" not in cur
            and (
                "myaccount" in cur
                or "nol.yanolja" in cur
                or "nol.interpark" in cur
            )
        )

    # ── 안심예매 캡챠 (로그인 전 메인 페이지) ──
    def _handle_page_captcha(self):
        drv = self.driver
        drv.switch_to.default_content()
        for attempt in range(10):
            src = self._page_src()
            if "문자를 입력해주세요" not in src and "안심예매" not in src:
                return True
            self.log("안심예매 보안문자를 입력해주세요 →")
            ans = self._ask(timeout=60)
            if not ans:
                self.log("입력 시간 초과"); return False
            self.log(f"→ {ans}")
            try:
                inp = None
                for sel in [
                    "input[placeholder*='문자']",
                    "#captcha_input",
                    "input[type='text']",
                ]:
                    try:
                        inp = drv.find_element(By.CSS_SELECTOR, sel)
                        break
                    except Exception:
                        pass
                if not inp:
                    self.log("입력창을 찾지 못했습니다"); return False
                inp.clear()
                inp.send_keys(ans)
                self._wait(0.3)
                for bsel in [
                    "button[type='submit']",
                    ".btn_confirm", ".btn_ok", "button",
                ]:
                    try:
                        drv.find_element(By.CSS_SELECTOR, bsel).click()
                        break
                    except Exception:
                        pass
                self._wait(1.2)
            except Exception as e:
                self.log(f"캡챠 입력 오류: {e}"); return False
            if "문자를 입력해주세요" not in self._page_src():
                self.log("→ 통과"); return True
            self.log(f"캡챠 재시도 ({attempt+1}/10)")
        return False

    # ── 예매 iframe 캡챠 ───────────────────────
    def _handle_iframe_captcha(self):
        drv  = self.driver
        wait = WebDriverWait(drv, 6)
        for attempt in range(10):
            self._wait(0.3)
            self._switch_frame("ifrmSeat", "ifrmCaptcha")
            cap = None
            for sel in ["#imgCaptcha", "img[id*='captcha' i]"]:
                try:
                    cap = wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                    )
                    break
                except Exception:
                    pass
            if cap is None:
                drv.switch_to.default_content()
                return True
            self.log("보안 문자를 입력해주세요 →")
            drv.switch_to.default_content()
            ans = self._ask(timeout=60)
            if not ans:
                self.log("입력 시간 초과"); return False
            self.log(f"→ {ans}")
            self._switch_frame("ifrmSeat", "ifrmCaptcha")
            try:
                try:
                    drv.find_element(
                        By.XPATH, "//div[@class='validationTxt']//span"
                    ).click()
                except Exception:
                    pass
                inp = drv.find_element(By.ID, "txtCaptcha")
                inp.clear()
                inp.send_keys(ans)
                self._wait(0.3)
                drv.execute_script("fnCheck();")
                self._wait(0.8)
            except Exception as e:
                self.log(f"보안문자 입력 오류: {e}")
                drv.switch_to.default_content()
                continue
            page = drv.page_source
            if "validationTxt alert" in page or "다시 입력" in page:
                self.log(f"오류 - 재시도 ({attempt+1}/10)")
                try:
                    drv.execute_script("fnCapchaRefresh();")
                except Exception:
                    pass
                drv.switch_to.default_content()
                self._wait(0.5)
            else:
                self.log("→ 보안문자 통과")
                drv.switch_to.default_content()
                return True
        drv.switch_to.default_content()
        return False

    # ── 좌석 등급 선택 ─────────────────────────
    def _ask_grade(self):
        self.log("좌석 등급을 선택해주세요:")
        self.log("1. 모두")
        for i, g in enumerate(GRADES, start=2):
            self.log(f"{i}. {g}")
        ans = self._ask(timeout=120)
        if ans is None:
            self.log("시간 초과 → 모두로 진행"); return 0
        self.log(f"→ {ans}")
        try:
            n = int(ans)
        except Exception:
            return 0
        if n == 1:
            return 0
        if 2 <= n <= len(GRADES) + 1:
            return n - 1   # GRADES 인덱스 (1~6)
        return 0

    # ── 구역 목록 파싱 ─────────────────────────
    def _get_zones(self, grade_idx):
        drv = self.driver
        drv.switch_to.default_content()
        self._switch_frame("ifrmSeat", "mainFrame")
        zones = []
        try:
            bs = BeautifulSoup(drv.page_source, "html.parser")
            kw = GRADES[grade_idx - 1] if grade_idx >= 1 else None
            for area in bs.find_all("area"):
                title = area.get("title") or area.get("alt") or ""
                if not title:
                    continue
                if kw is None or kw in title:
                    zones.append(title)
            if not zones:
                for el in bs.find_all(["span", "td", "li"]):
                    t = el.get_text(strip=True)
                    if "영역" in t or "구역" in t:
                        zones.append(t)
        except Exception:
            pass
        drv.switch_to.default_content()
        seen, unique = set(), []
        for z in zones:
            if z not in seen:
                seen.add(z)
                unique.append(z)
        return unique

    # ── 구역 선택 ──────────────────────────────
    def _ask_zones(self, grade_idx):
        zone_list = self._get_zones(grade_idx)
        if not zone_list:
            self.log("구역 목록을 읽지 못했습니다. 직접 입력 (예: 001영역,002영역)")
        else:
            for i, z in enumerate(zone_list, start=1):
                self.log(f"{i}. {z}")
        self.log("→ 번호(콤마 구분) 또는 직접 입력")
        ans = self._ask(timeout=120)
        if not ans:
            return zone_list
        self.log(f"→ {ans}")
        selected = []
        for part in ans.split(","):
            part = part.strip()
            try:
                idx = int(part) - 1
                if 0 <= idx < len(zone_list):
                    selected.append(zone_list[idx])
            except Exception:
                if part:
                    selected.append(part)
        return selected if selected else zone_list

    # ── 좌석 클릭 시도 ─────────────────────────
    def _try_select_seat(self, grade_idx):
        drv = self.driver
        kw  = GRADES[grade_idx - 1].upper() if grade_idx >= 1 else None
        try:
            seats = drv.find_elements(
                By.CSS_SELECTOR,
                "img.stySeat, span[onclick*='Seat'], td[onclick*='Seat']",
            )
            for seat in seats:
                alt   = seat.get_attribute("alt")   or ""
                title = seat.get_attribute("title") or ""
                text  = (alt + title).upper()
                if kw and kw not in text:
                    continue
                drv.execute_script("arguments[0].click();", seat)
                self.log(f"좌석 선택: {(alt or title)[:30]}")
                self._wait(0.3)
                return True
        except Exception:
            pass
        return False

    # ── 퍼즐 슬라이더 ──────────────────────────
    def _solve_puzzle(self):
        drv = self.driver
        drv.switch_to.default_content()
        self._switch_frame("ifrmSeat", "mainFrame")
        found = False
        for sel in [".slider_wrap", ".puzzle_wrap",
                    "[class*='slider']", "[class*='puzzle']"]:
            try:
                if drv.find_element(By.CSS_SELECTOR, sel).is_displayed():
                    found = True; break
            except Exception:
                pass
        if not found:
            try:
                if "슬라이더를 밀어" in drv.page_source:
                    found = True
            except Exception:
                pass
        if not found:
            drv.switch_to.default_content(); return

        bg_path, pc_path, offset = "puzzle_bg.png", "puzzle_piece.png", 140
        bg_el = pc_el = None
        for s in ["#captcha_bg","#puzzle_bg","img[id*='bg']",".puzzle_bg",".bg_img"]:
            try: bg_el = drv.find_element(By.CSS_SELECTOR, s); break
            except Exception: pass
        for s in ["#captcha_piece","#puzzle_piece","img[id*='piece']",".puzzle_piece"]:
            try: pc_el = drv.find_element(By.CSS_SELECTOR, s); break
            except Exception: pass
        if bg_el and pc_el:
            try:
                bg_el.screenshot(bg_path)
                pc_el.screenshot(pc_path)
                offset = self._calc_offset(bg_path, pc_path)
            except Exception:
                pass
        self.log(f"[퍼즐 감지 목표 위치: {offset}px]")

        slider = None
        for s in [".btn_slide_right",".slide_btn",".slider_btn",
                  "div[class*='slider'] span","#nc_1__scale_text"]:
            try: slider = drv.find_element(By.CSS_SELECTOR, s); break
            except Exception: pass
        if slider:
            try:
                ac = ActionChains(drv)
                ac.click_and_hold(slider).pause(0.3)
                for _ in range(20):
                    ac.move_by_offset(offset / 20, 0).pause(0.02)
                ac.release().perform()
                self._wait(1.2)
            except Exception as e:
                self.log(f"슬라이더 오류: {e}")
        drv.switch_to.default_content()

    def _calc_offset(self, bg_path, pc_path):
        try:
            bg    = np.array(Image.open(bg_path).convert("L"), dtype=np.float32)
            piece = np.array(Image.open(pc_path).convert("L"), dtype=np.float32)
            ph, pw = piece.shape
            bh, bw = bg.shape
            best_x, best_score = 0, float("inf")
            for x in range(0, bw - pw, 2):
                score = float(np.mean(np.abs(bg[:ph, x:x+pw] - piece)))
                if score < best_score:
                    best_score = score; best_x = x
            return best_x
        except Exception:
            return 140

    # ── 구역 순회 ──────────────────────────────
    def _rotate_zones(self, zone_names, grade_idx):
        drv   = self.driver
        cycle = 0
        self.log(f"구역 순회 시작 (딜레이 {self.delay}초)")
        while True:
            for zone in zone_names:
                self._wait(0)
                drv.switch_to.default_content()
                self._switch_frame("ifrmSeat", "mainFrame")
                clicked = False
                try:
                    for area in drv.find_elements(By.TAG_NAME, "area"):
                        t = area.get_attribute("title") or area.get_attribute("alt") or ""
                        if zone in t or t in zone:
                            drv.execute_script("arguments[0].click();", area)
                            clicked = True; break
                except Exception:
                    pass
                if not clicked:
                    try:
                        for area in drv.find_elements(By.TAG_NAME, "area"):
                            href = area.get_attribute("href") or ""
                            if zone.replace("영역","").strip() in href:
                                drv.execute_script(href.replace("javascript:", ""))
                                clicked = True; break
                    except Exception:
                        pass
                self._wait(self.delay)
                self._solve_puzzle()
                if self._try_select_seat(grade_idx):
                    drv.switch_to.default_content()
                    return
                drv.switch_to.default_content()
            cycle += 1
            if cycle % 5 == 0:
                self.log(f"구역 순회 {cycle}바퀴 완료 - 계속 탐색 중...")

    # ── 좌석선택완료 ───────────────────────────
    def _click_complete(self):
        drv = self.driver
        self.log("좌석선택완료 클릭")
        drv.switch_to.default_content()
        self._switch_frame("ifrmSeat", "mainFrame")
        for fn in ["fnSelect()", "fnComplete()", "fnSelectSeat()"]:
            try:
                drv.execute_script(fn)
                self._wait(0.5); break
            except Exception:
                pass
        try:
            btn = drv.find_element(
                By.XPATH,
                "//a[contains(text(),'좌석선택완료')]"
                " | //button[contains(text(),'좌석선택완료')]",
            )
            drv.execute_script("arguments[0].click();", btn)
        except Exception:
            pass
        drv.switch_to.default_content()
        self._wait(1.5)

    # ── 결제 대기 ──────────────────────────────
    def _wait_payment(self):
        drv = self.driver
        self.log("결제 페이지 대기 - 소리 알림 시작")
        def _beep():
            for _ in range(10):
                try:
                    winsound.Beep(1000, 400)
                    time.sleep(0.15)
                    winsound.Beep(1300, 400)
                    time.sleep(0.3)
                except Exception:
                    break
        threading.Thread(target=_beep, daemon=True).start()
        keywords = ["payment", "pay", "order", "checkout", "BookEnd", "완료"]
        for _ in range(1800):
            self._wait(1)
            try:
                if any(k in drv.current_url for k in keywords):
                    self.log("✅ 결제 완료!"); return
            except Exception:
                pass
        self.log("결제 대기 시간 초과")

    # ── 메인 흐름 ──────────────────────────────
    def run(self):
        try:
            self.log("매크로 실행 시작")
            self.log("로그인을 완료해 주세요.")

            # 1) 로그인 대기 (최대 5분)
            for _ in range(300):
                self._wait(1)
                src = self._page_src()
                if "문자를 입력해주세요" in src or "안심예매" in src:
                    self._handle_page_captcha()
                    continue
                if self._is_logged_in():
                    break
            else:
                self.log("로그인 대기 시간 초과"); return
            self.log("→ 로그인 완료")

            # 2) 예매 페이지 진입 대기 (최대 30분)
            self.log("원하는 공연 페이지에서 [예매하기] 버튼을 눌러 주세요.")
            BOOKING_KW = ["poticket", "Book", "motickets", "step2", "ticket"]
            for _ in range(1800):
                self._wait(1)
                cur = self._cur_url()
                src = self._page_src()
                # 예매 대기 중 안심예매 캡챠가 뜨면 즉시 처리
                if "문자를 입력해주세요" in src or "안심예매" in src:
                    self._handle_page_captcha()
                    self._wait(1)
                    continue
                if any(k in cur for k in BOOKING_KW):
                    break
            self._wait(1.5)

            # 3) iframe 캡챠
            self._handle_iframe_captcha()
            self._wait(0.5)

            # 5) 등급 선택
            grade_idx = self._ask_grade()
            self._wait(0.3)

            # 6) 구역 선택
            zones = self._ask_zones(grade_idx)
            self.log(f"선택 구역: {', '.join(zones) if zones else '전체'}")
            self._wait(0.3)

            # 7) 구역 순회 + 좌석 클릭
            self._rotate_zones(zones, grade_idx)

            # 8) 좌석선택완료
            self._click_complete()

            # 9) 결제 대기
            self._wait_payment()

        except InterruptedError:
            self.log("매크로 중단됨")
        except Exception as e:
            self.log(f"오류: {e}\n{traceback.format_exc()}")


# ───────────────────────────────────────────────
#  컨트롤 창
# ───────────────────────────────────────────────
class ControlWindow(QWidget):
    def __init__(self, driver, delay):
        super().__init__()
        self.setWindowTitle("인터파크티켓 취소표 매크로")
        self.setFont(QFont("맑은 고딕", 9))
        self.setFixedWidth(310)

        self._sig    = Signals()
        self._thread = MacroThread(driver, delay, self._sig)
        self._paused = False

        self._sig.log_signal.connect(self._append_log)
        self._sig.captcha_signal.connect(self._show_input)
        self._sig.input_hide.connect(self._hide_input)

        root = QVBoxLayout()
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # 로그 박스
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(130)
        self.log_box.setFont(QFont("맑은 고딕", 9))
        self.log_box.setStyleSheet(
            "background:#ffffff; color:#222; border:1px solid #ccc;"
        )
        root.addWidget(self.log_box)

        # 입력 행 (평소에는 숨김)
        self.input_row = QWidget()
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("보안문자 / 번호 입력")
        self.input_edit.setFixedHeight(28)
        self.input_edit.returnPressed.connect(self._submit)
        self.input_btn = QPushButton("입력완료")
        self.input_btn.setFixedSize(64, 28)
        self.input_btn.setStyleSheet(
            "background:#4a90d9; color:white; font-weight:bold; border-radius:3px;"
        )
        self.input_btn.clicked.connect(self._submit)
        row_layout.addWidget(self.input_edit)
        row_layout.addWidget(self.input_btn)
        self.input_row.setLayout(row_layout)
        self.input_row.hide()
        root.addWidget(self.input_row)

        # 버튼 행
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
        root.addLayout(btn_row)

        self.setLayout(root)
        self.adjustSize()
        self._thread.start()

    def _append_log(self, msg):
        self.log_box.append(msg)
        sb = self.log_box.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _show_input(self):
        self.input_edit.clear()
        self.input_row.show()
        self.input_edit.setFocus()
        self.adjustSize()

    def _hide_input(self):
        self.input_row.hide()
        self.adjustSize()

    def _submit(self):
        self._thread.set_answer(self.input_edit.text().strip())

    def _on_stop(self):
        self._thread.stop()
        self.btn_stop.setEnabled(False)
        self.btn_pause.setEnabled(False)

    def _on_pause(self):
        self._paused = self._thread.toggle_pause()
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


# ───────────────────────────────────────────────
#  로그인 창
# ───────────────────────────────────────────────
class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("인터파크티켓 취소표 매크로")
        self.setFixedWidth(300)
        self.setFont(QFont("맑은 고딕", 10))
        self._ctrl = None

        root = QVBoxLayout()
        root.setSpacing(8)
        root.setContentsMargins(16, 16, 16, 16)

        # 로그인 탭
        root.addWidget(QLabel("로그인"))
        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        self._tab_btns = [
            QPushButton("인터파크"),
            QPushButton("카카오"),
            QPushButton("네이버"),
        ]
        self._tab_grp = QButtonGroup(self)
        for i, b in enumerate(self._tab_btns):
            b.setCheckable(True)
            b.setFixedHeight(30)
            self._tab_grp.addButton(b, i)
            tab_row.addWidget(b)
        self._tab_btns[0].setChecked(True)
        self._tab_grp.buttonClicked.connect(lambda _: self._update_tabs())
        self._update_tabs()
        root.addLayout(tab_row)

        # ID
        row = QHBoxLayout()
        lbl = QLabel("ID"); lbl.setFixedWidth(40)
        self.edit_id = QLineEdit(); self.edit_id.setFixedHeight(28)
        row.addWidget(lbl); row.addWidget(self.edit_id)
        root.addLayout(row)

        # PW
        row = QHBoxLayout()
        lbl = QLabel("PW"); lbl.setFixedWidth(40)
        self.edit_pw = QLineEdit()
        self.edit_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_pw.setFixedHeight(28)
        row.addWidget(lbl); row.addWidget(self.edit_pw)
        root.addLayout(row)

        # 딜레이
        row = QHBoxLayout()
        lbl = QLabel("딜레이"); lbl.setFixedWidth(44)
        self.spin = QSpinBox()
        self.spin.setRange(1, 60)
        self.spin.setValue(1)
        self.spin.setFixedHeight(28)
        row.addWidget(lbl); row.addWidget(self.spin); row.addStretch()
        root.addLayout(row)

        # 유효기간
        lbl_exp = QLabel(f"유효기간: {EXPIRE_DATE}")
        lbl_exp.setAlignment(Qt.AlignmentFlag.AlignRight)
        lbl_exp.setStyleSheet("color:#888; font-size:9px;")
        root.addWidget(lbl_exp)

        # 시작하기
        self.btn_start = QPushButton("시작하기")
        self.btn_start.setFixedHeight(36)
        self.btn_start.setStyleSheet(
            "background:#3c3c3c; color:white;"
            " font-weight:bold; font-size:12px; border-radius:4px;"
        )
        self.btn_start.clicked.connect(self._on_start)
        root.addWidget(self.btn_start)

        self.setLayout(root)

    def _update_tabs(self):
        for b in self._tab_btns:
            if b.isChecked():
                b.setStyleSheet(
                    "background:#4a90d9; color:white;"
                    " font-weight:bold; border:none; border-radius:3px;"
                )
            else:
                b.setStyleSheet(
                    "background:#e0e0e0; color:#333;"
                    " border:none; border-radius:3px;"
                )

    def _on_start(self):
        delay = self.spin.value()
        try:
            opts = webdriver.ChromeOptions()
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
            drv = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=opts,
            )
            drv.set_page_load_timeout(30)
            drv.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"Chrome 실행 실패:\n{e}")
            return

        try:
            drv.get(LOGIN_URL)
        except Exception:
            pass

        self._ctrl = ControlWindow(drv, delay)
        self._ctrl.show()
        self.hide()


# ───────────────────────────────────────────────
#  진입점
# ───────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("맑은 고딕", 10))
    win = LoginWindow()
    win.show()
    sys.exit(app.exec())
