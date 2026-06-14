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
    log_signal   = Signal(str)
    show_input   = Signal()
    hide_input   = Signal()


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

    def stop(self):
        self._stop = True

    def toggle_pause(self):
        self._pause = not self._pause
        return self._pause

    def set_answer(self, text):
        self._answer = text
        self._ev.set()

    # ── 로그 ──────────────────────────────────
    def log(self, msg):
        ts = time.strftime("%Y/%m/%d %H:%M:%S")
        self.sig.log_signal.emit(f"[{ts}] {msg}")

    # ── 대기 ──────────────────────────────────
    def _wait(self, sec):
        end = time.time() + sec
        while time.time() < end:
            if self._stop: raise InterruptedError
            while self._pause:
                if self._stop: raise InterruptedError
                time.sleep(0.1)
            time.sleep(0.05)

    # ── GUI 입력 요청 ─────────────────────────
    def _ask(self, timeout=120):
        self._ev.clear()
        self.sig.show_input.emit()
        ok  = self._ev.wait(timeout=timeout)
        ans = self._answer
        self.sig.hide_input.emit()
        return ans if ok else None

    # ── URL / 소스 헬퍼 ──────────────────────
    def _url(self):
        try: return self.driver.current_url
        except: return ""

    def _src(self):
        try: return self.driver.page_source
        except: return ""

    # ── 로그인 완료 감지 ──────────────────────
    # 로그인 후 URL: nol.interpark.com 또는 nol.yanolja.com 또는 myaccount
    def _is_logged_in(self):
        url = self._url()
        return (
            "nol.interpark.com" in url or
            "nol.yanolja.com"   in url or
            ("accounts.yanolja.com" in url and "myaccount" in url)
        )

    # ── 안심예매 캡챠 팝업 감지 ──────────────
    def _captcha_visible(self):
        try:
            src = self._src()
            return "안심예매" in src and "문자를 입력해주세요" in src
        except: return False

    # ── 안심예매 캡챠 처리 ────────────────────
    # 팝업에 직접 텍스트 입력 → 입력완료 클릭
    def _handle_captcha(self):
        drv = self.driver
        drv.switch_to.default_content()

        for attempt in range(10):
            if not self._captcha_visible():
                return True

            self.log("보안 문자를 입력해주세요. 없을 경우, 0을 입력해주세요 →")
            ans = self._ask(timeout=90)
            if ans is None:
                self.log("입력 시간 초과"); return False
            self.log(f"→ {ans}")

            # 0 입력 시 캡챠 없음으로 처리
            if ans.strip() == "0":
                return True

            try:
                # 캡챠 입력창 찾기
                inp = None
                for sel in [
                    "input[placeholder*='문자를 입력해주세요']",
                    "input[placeholder*='문자']",
                    ".captcha_input input",
                    "#captchaInput",
                    "input[type='text']",
                ]:
                    try:
                        el = drv.find_element(By.CSS_SELECTOR, sel)
                        if el.is_displayed(): inp = el; break
                    except: pass

                if not inp:
                    self.log("입력창을 찾지 못했습니다"); return False

                inp.clear()
                inp.send_keys(ans)
                self._wait(0.3)

                # 입력완료 버튼 클릭
                confirmed = False
                for bsel in [
                    "//button[contains(text(),'입력완료')]",
                    "//a[contains(text(),'입력완료')]",
                ]:
                    try:
                        btn = drv.find_element(By.XPATH, bsel)
                        drv.execute_script("arguments[0].click();", btn)
                        confirmed = True; break
                    except: pass

                if not confirmed:
                    for bsel in [".btn_ok", ".btn_confirm", "button.confirm"]:
                        try:
                            drv.find_element(By.CSS_SELECTOR, bsel).click()
                            confirmed = True; break
                        except: pass

                self._wait(1.5)

            except Exception as e:
                self.log(f"캡챠 처리 오류: {e}")
                continue

            if not self._captcha_visible():
                self.log("→ 캡챠 통과"); return True

            self.log(f"캡챠 재시도 ({attempt+1}/10)")
            # 날짜 다시 선택 후 재시도
            try:
                drv.find_element(By.XPATH, "//button[contains(text(),'날짜 다시 선택')]").click()
                self._wait(1)
            except: pass

        return False

    # ── 좌석 등급 선택 ────────────────────────
    def _ask_grade(self):
        self.log("좌석 등급을 선택하세요:")
        self.log("1. 모두")
        for i, g in enumerate(GRADES, 2):
            self.log(f"{i}. {g}")
        ans = self._ask(timeout=120)
        if ans is None:
            self.log("시간 초과 → 모두로 진행"); return 0
        self.log(f"→ {ans}")
        try: n = int(ans)
        except: return 0
        if n == 1: return 0
        if 2 <= n <= len(GRADES) + 1: return n - 1
        return 0

    # ── iframe 전환 헬퍼 ──────────────────────
    def _to_frame(self, *ids):
        self.driver.switch_to.default_content()
        for fid in ids:
            try:
                self.driver.switch_to.frame(
                    self.driver.find_element(By.ID, fid)
                )
                return True
            except: pass
        return False

    # ── 구역 목록 파싱 ────────────────────────
    def _get_zones(self, grade_idx):
        drv = self.driver
        drv.switch_to.default_content()
        self._to_frame("ifrmSeat", "mainFrame")
        kw    = GRADES[grade_idx - 1] if grade_idx >= 1 else None
        zones = []
        try:
            bs = BeautifulSoup(drv.page_source, "html.parser")
            for area in bs.find_all("area"):
                t = area.get("title") or area.get("alt") or ""
                if t and (kw is None or kw in t):
                    zones.append(t)
            if not zones:
                for el in bs.find_all(["span","td","li"]):
                    t = el.get_text(strip=True)
                    if "영역" in t or "구역" in t:
                        zones.append(t)
        except: pass
        drv.switch_to.default_content()
        seen, unique = set(), []
        for z in zones:
            if z not in seen: seen.add(z); unique.append(z)
        return unique

    # ── 구역 선택 ─────────────────────────────
    def _ask_zones(self, grade_idx):
        zone_list = self._get_zones(grade_idx)
        if not zone_list:
            self.log("구역 목록을 읽지 못했습니다. 직접 입력 (예: 001영역,002영역)")
        else:
            for i, z in enumerate(zone_list, 1):
                self.log(f"{i}. {z}")
        self.log("→ 번호(콤마 구분) 또는 직접 입력")
        ans = self._ask(timeout=120)
        if not ans: return zone_list
        self.log(f"→ {ans}")
        selected = []
        for part in ans.split(","):
            part = part.strip()
            try:
                idx = int(part) - 1
                if 0 <= idx < len(zone_list):
                    selected.append(zone_list[idx])
            except:
                if part: selected.append(part)
        return selected if selected else zone_list

    # ── 좌석 클릭 ─────────────────────────────
    def _click_seat(self, grade_idx):
        drv = self.driver
        kw  = GRADES[grade_idx - 1].upper() if grade_idx >= 1 else None
        try:
            seats = drv.find_elements(
                By.CSS_SELECTOR,
                "img.stySeat, span[onclick*='Seat'], td[onclick*='Seat']"
            )
            for seat in seats:
                alt   = seat.get_attribute("alt")   or ""
                title = seat.get_attribute("title") or ""
                if kw and kw not in (alt + title).upper(): continue
                drv.execute_script("arguments[0].click();", seat)
                self.log(f"좌석 선택: {(alt or title)[:30]}")
                self._wait(0.3); return True
        except: pass
        return False

    # ── 퍼즐 슬라이더 ─────────────────────────
    def _solve_puzzle(self):
        drv = self.driver
        drv.switch_to.default_content()
        self._to_frame("ifrmSeat", "mainFrame")
        found = False
        for sel in [".slider_wrap",".puzzle_wrap","[class*='slider']","[class*='puzzle']"]:
            try:
                if drv.find_element(By.CSS_SELECTOR, sel).is_displayed():
                    found = True; break
            except: pass
        if not found:
            try: found = "슬라이더를 밀어" in drv.page_source
            except: pass
        if not found: drv.switch_to.default_content(); return

        offset, bg_path, pc_path = 140, "puzzle_bg.png", "puzzle_pc.png"
        bg_el = pc_el = None
        for s in ["#captcha_bg","#puzzle_bg","img[id*='bg']",".puzzle_bg"]:
            try: bg_el = drv.find_element(By.CSS_SELECTOR, s); break
            except: pass
        for s in ["#captcha_piece","#puzzle_piece","img[id*='piece']",".puzzle_piece"]:
            try: pc_el = drv.find_element(By.CSS_SELECTOR, s); break
            except: pass
        if bg_el and pc_el:
            try:
                bg_el.screenshot(bg_path); pc_el.screenshot(pc_path)
                bg = np.array(Image.open(bg_path).convert("L"), dtype=np.float32)
                pc = np.array(Image.open(pc_path).convert("L"), dtype=np.float32)
                ph, pw = pc.shape; bh, bw = bg.shape
                best_x, best_sc = 0, float("inf")
                for x in range(0, bw - pw, 2):
                    sc = float(np.mean(np.abs(bg[:ph, x:x+pw] - pc)))
                    if sc < best_sc: best_sc = sc; best_x = x
                offset = best_x
            except: pass
        self.log(f"[퍼즐 목표: {offset}px]")
        slider = None
        for s in [".btn_slide_right",".slide_btn",".slider_btn",
                  "div[class*='slider'] span","#nc_1__scale_text"]:
            try: slider = drv.find_element(By.CSS_SELECTOR, s); break
            except: pass
        if slider:
            try:
                ac = ActionChains(drv)
                ac.click_and_hold(slider).pause(0.3)
                for _ in range(20): ac.move_by_offset(offset/20, 0).pause(0.02)
                ac.release().perform(); self._wait(1.2)
            except Exception as e: self.log(f"슬라이더 오류: {e}")
        drv.switch_to.default_content()

    # ── 구역 순회 ─────────────────────────────
    def _rotate_zones(self, zones, grade_idx):
        drv, cycle = self.driver, 0
        self.log(f"구역 순회 시작 (딜레이 {self.delay}초)")
        while True:
            for zone in zones:
                self._wait(0)
                drv.switch_to.default_content()
                self._to_frame("ifrmSeat", "mainFrame")
                clicked = False
                try:
                    for area in drv.find_elements(By.TAG_NAME, "area"):
                        t = area.get_attribute("title") or area.get_attribute("alt") or ""
                        if zone in t or t in zone:
                            drv.execute_script("arguments[0].click();", area)
                            clicked = True; break
                except: pass
                if not clicked:
                    try:
                        for area in drv.find_elements(By.TAG_NAME, "area"):
                            href = area.get_attribute("href") or ""
                            if zone.replace("영역","").strip() in href:
                                drv.execute_script(href.replace("javascript:",""))
                                clicked = True; break
                    except: pass
                self._wait(self.delay)
                self._solve_puzzle()
                if self._click_seat(grade_idx):
                    drv.switch_to.default_content(); return
                drv.switch_to.default_content()
            cycle += 1
            if cycle % 5 == 0:
                self.log(f"구역 순회 {cycle}바퀴 완료...")

    # ── 좌석선택완료 ──────────────────────────
    def _click_complete(self):
        drv = self.driver
        self.log("좌석선택완료 클릭")
        drv.switch_to.default_content()
        self._to_frame("ifrmSeat", "mainFrame")
        for fn in ["fnSelect()", "fnComplete()", "fnSelectSeat()"]:
            try: drv.execute_script(fn); self._wait(0.5); break
            except: pass
        try:
            btn = drv.find_element(By.XPATH,
                "//a[contains(text(),'좌석선택완료')]"
                "|//button[contains(text(),'좌석선택완료')]")
            drv.execute_script("arguments[0].click();", btn)
        except: pass
        drv.switch_to.default_content()
        self._wait(1.5)

    # ── 결제 대기 ─────────────────────────────
    def _wait_payment(self):
        self.log("결제 페이지 대기 - 소리 알림 시작")
        def _beep():
            for _ in range(10):
                try:
                    winsound.Beep(1000, 400); time.sleep(0.15)
                    winsound.Beep(1300, 400); time.sleep(0.3)
                except: break
        threading.Thread(target=_beep, daemon=True).start()
        kw = ["payment","pay","order","checkout","BookEnd","완료"]
        for _ in range(1800):
            self._wait(1)
            try:
                if any(k in self.driver.current_url for k in kw):
                    self.log("✅ 결제 완료!"); return
            except: pass
        self.log("결제 대기 시간 초과")

    # ── 메인 흐름 ─────────────────────────────
    def run(self):
        try:
            # ① 로그인 대기
            self.log("매크로 실행 시작")
            self.log("로그인을 완료해 주세요.")
            for _ in range(300):
                self._wait(1)
                if self._is_logged_in(): break
            else:
                self.log("로그인 대기 시간 초과"); return
            self.log("→ 로그인 완료")

            # ② 예매 페이지 대기
            self.log("원하시는 링크에 들어가서 [예매하기] 버튼을 눌러 주세요.")
            for _ in range(1800):
                self._wait(1)
                url = self._url()
                if "poticket" in url or "Book" in url or "motickets" in url:
                    break
            self._wait(2)

            # ③ 안심예매 캡챠 처리
            if self._captcha_visible():
                self._handle_captcha()
                self._wait(1)

            # ④ 좌석 등급 선택
            grade_idx = self._ask_grade()
            self._wait(0.3)

            # ⑤ 구역 선택
            zones = self._ask_zones(grade_idx)
            self.log(f"선택 구역: {', '.join(zones) if zones else '전체'}")
            self._wait(0.3)

            # ⑥ 구역 순회 + 좌석 클릭
            self._rotate_zones(zones, grade_idx)

            # ⑦ 좌석선택완료
            self._click_complete()

            # ⑧ 결제 대기
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

        self._sig.log_signal.connect(self._on_log)
        self._sig.show_input.connect(self._show_input)
        self._sig.hide_input.connect(self._hide_input)

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

        # 입력 행 (기본 숨김)
        self.input_row = QWidget()
        rl = QHBoxLayout()
        rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(4)
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
        rl.addWidget(self.input_edit); rl.addWidget(self.input_btn)
        self.input_row.setLayout(rl)
        self.input_row.hide()
        root.addWidget(self.input_row)

        # 중단/일시정지 버튼
        bl = QHBoxLayout(); bl.setSpacing(6)
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
        bl.addWidget(self.btn_stop); bl.addWidget(self.btn_pause)
        root.addLayout(bl)

        self.setLayout(root)
        self.adjustSize()
        self._thread.start()

    def _on_log(self, msg):
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

        root.addWidget(QLabel("로그인"))

        # 인터파크 / 카카오 / 네이버 탭
        tab_row = QHBoxLayout(); tab_row.setSpacing(0)
        self._tab_btns = [
            QPushButton("인터파크"),
            QPushButton("카카오"),
            QPushButton("네이버"),
        ]
        self._tab_grp = QButtonGroup(self)
        for i, b in enumerate(self._tab_btns):
            b.setCheckable(True); b.setFixedHeight(30)
            self._tab_grp.addButton(b, i); tab_row.addWidget(b)
        self._tab_btns[0].setChecked(True)
        self._tab_grp.buttonClicked.connect(lambda _: self._update_tabs())
        self._update_tabs()
        root.addLayout(tab_row)

        # ID
        r = QHBoxLayout()
        lb = QLabel("ID"); lb.setFixedWidth(40)
        self.edit_id = QLineEdit(); self.edit_id.setFixedHeight(28)
        r.addWidget(lb); r.addWidget(self.edit_id); root.addLayout(r)

        # PW
        r = QHBoxLayout()
        lb = QLabel("PW"); lb.setFixedWidth(40)
        self.edit_pw = QLineEdit()
        self.edit_pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit_pw.setFixedHeight(28)
        r.addWidget(lb); r.addWidget(self.edit_pw); root.addLayout(r)

        # 딜레이
        r = QHBoxLayout()
        lb = QLabel("딜레이"); lb.setFixedWidth(44)
        self.spin = QSpinBox()
        self.spin.setRange(1, 60); self.spin.setValue(1); self.spin.setFixedHeight(28)
        r.addWidget(lb); r.addWidget(self.spin); r.addStretch(); root.addLayout(r)

        # 유효기간
        lbl = QLabel(f"유효기간: {EXPIRE_DATE}")
        lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        lbl.setStyleSheet("color:#888; font-size:9px;")
        root.addWidget(lbl)

        # 시작하기
        self.btn_start = QPushButton("시작하기")
        self.btn_start.setFixedHeight(36)
        self.btn_start.setStyleSheet(
            "background:#3c3c3c; color:white; font-weight:bold;"
            " font-size:12px; border-radius:4px;"
        )
        self.btn_start.clicked.connect(self._on_start)
        root.addWidget(self.btn_start)

        self.setLayout(root)

    def _update_tabs(self):
        for b in self._tab_btns:
            b.setStyleSheet(
                "background:#4a90d9; color:white; font-weight:bold;"
                " border:none; border-radius:3px;" if b.isChecked() else
                "background:#e0e0e0; color:#333; border:none; border-radius:3px;"
            )

    def _on_start(self):
        delay = self.spin.value()
        try:
            opts = webdriver.ChromeOptions()
            opts.add_argument("--disable-blink-features=AutomationControlled")
            opts.add_experimental_option("excludeSwitches", ["enable-automation"])
            opts.add_experimental_option("useAutomationExtension", False)
            drv = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()), options=opts
            )
            drv.set_page_load_timeout(30)
            drv.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"}
            )
        except Exception as e:
            QMessageBox.critical(self, "오류", f"Chrome 실행 실패:\n{e}"); return

        try: drv.get(LOGIN_URL)
        except: pass

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
