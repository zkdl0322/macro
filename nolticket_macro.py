# -*- encoding:utf8 -*-

import sys
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QSpinBox, QPushButton, QButtonGroup
)

EXPIRE_DATE = "~26.09.30"


class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("인터파크티켓 취소표 매크로")
        self.setFixedWidth(300)
        self.setFont(QFont("맑은 고딕", 10))

        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(16, 16, 16, 16)

        # ── 로그인 탭 버튼
        lbl_login = QLabel("로그인")
        lbl_login.setFont(QFont("맑은 고딕", 9))
        layout.addWidget(lbl_login)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(0)
        self.btn_interpark = QPushButton("인터파크")
        self.btn_kakao     = QPushButton("카카오")
        self.btn_naver     = QPushButton("네이버")

        self._tab_group = QButtonGroup(self)
        self._tab_buttons = [self.btn_interpark, self.btn_kakao, self.btn_naver]

        for i, btn in enumerate(self._tab_buttons):
            btn.setCheckable(True)
            btn.setFixedHeight(30)
            self._tab_group.addButton(btn, i)
            tab_row.addWidget(btn)

        self.btn_interpark.setChecked(True)
        self._tab_group.buttonClicked.connect(self._on_tab)
        self._apply_tab_style()
        layout.addLayout(tab_row)

        # ── ID / PW
        form_layout = QVBoxLayout()
        form_layout.setSpacing(6)

        row_id = QHBoxLayout()
        lbl_id = QLabel("ID")
        lbl_id.setFixedWidth(40)
        self.edit_id = QLineEdit()
        self.edit_id.setFixedHeight(28)
        row_id.addWidget(lbl_id)
        row_id.addWidget(self.edit_id)
        form_layout.addLayout(row_id)

        row_pw = QHBoxLayout()
        lbl_pw = QLabel("PW")
        lbl_pw.setFixedWidth(40)
        self.edit_pw = QLineEdit()
        self.edit_pw.setEchoMode(QLineEdit.Password)
        self.edit_pw.setFixedHeight(28)
        row_pw.addWidget(lbl_pw)
        row_pw.addWidget(self.edit_pw)
        form_layout.addLayout(row_pw)

        layout.addLayout(form_layout)

        # ── 딜레이
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

        # ── 유효기간
        lbl_expire = QLabel(f"유효기간: {EXPIRE_DATE}")
        lbl_expire.setAlignment(Qt.AlignRight)
        lbl_expire.setStyleSheet("color: #888; font-size: 9px;")
        layout.addWidget(lbl_expire)

        # ── 시작하기 버튼
        self.btn_start = QPushButton("시작하기")
        self.btn_start.setFixedHeight(36)
        self.btn_start.setStyleSheet(
            "background:#3c3c3c; color:white; font-weight:bold; font-size:12px; border-radius:4px;"
        )
        self.btn_start.clicked.connect(self._on_start)
        layout.addWidget(self.btn_start)

        self.setLayout(layout)

    def _on_tab(self, btn):
        self._apply_tab_style()

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
        print(f"시작: login={login_type}, id={user_id}, delay={delay}")
        # TODO: 다음 단계 연결
        self.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("맑은 고딕", 10))
    win = LoginWindow()
    win.show()
    sys.exit(app.exec_())
