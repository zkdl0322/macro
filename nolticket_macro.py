# -*- encoding:utf8 -*-

import sys
import time
import threading
import traceback

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

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
    log_signal = pyqtSignal(str)

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

    def stop(self):  self._stop = True
    def pause(self):
        self._pause = not self._pause
        return self._pause

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

    def run(self):
        try:
            self.log("매크로 실행 시작")
            self.log("로그인을 완료해 주세요.")

            # 로그인 완료 대기 (최대 5분)
            for _ in range(300):
                self._wait(1)
                try:
                    cur = self.driver.current_url
                    # NOL 인터파크 로그인 완료 감지
                    if "login" not in cur and "accounts" not in cur:
                        self.log("로그인 감지 완료")
                        break
                except:
                    pass
            else:
                self.log("로그인 대기 시간 초과")
                return

            # TODO: 다음 단계 추가 예정

        except InterruptedError:
            self.log("매크로 중단됨")
        except Exception as e:
            self.log(f"오류: {e}")


# ──────────────────────────────────────────────
#  컨트롤 창 (매크로 실행 중 표시)
# ──────────────────────────────────────────────
class ControlWindow(QWidget):
    def __init__(self, driver, login_type, user_id, user_pw, delay):
        super().__init__()
        self.setWindowTitle("인터파크티켓 취소표 매크로")
        self.setFont(QFont("맑은 고딕", 9))
        self.setFixedWidth(310)
        self.setFixedHeight(190)

        self._sig    = Signals()
        self._thread = MacroThread(driver, login_type, user_id, user_pw, delay, self._sig)
        self._paused = False

        self._sig.log_signal.connect(self._append_log)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # 로그창
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("맑은 고딕", 9))
        self.log_box.setStyleSheet(
            "background:#ffffff; color:#222; border:1px solid #ccc;"
        )
        layout.addWidget(self.log_box)

        # 버튼
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
        self._thread.start()

    def _append_log(self, msg):
        self.log_box.append(msg)
        self.log_box.moveCursor(QTextCursor.End)

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

        # 브라우저 열기
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

        # NOL 인터파크 로그인 페이지 열기
        try:
            driver.get("https://accounts.yanolja.com/?clientId=inpark-pc&postProc=FULLSCREEN&origin=https%3A%2F%2Fnol.interpark.com")
        except:
            pass

        # 컨트롤 창 열기
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
