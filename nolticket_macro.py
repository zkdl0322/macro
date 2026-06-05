# -*- encoding:utf8 -*-

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import sys
import time
import traceback
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5 import QtCore


# ────────────────────────────────────────────
#  활동 로그
# ────────────────────────────────────────────
def log(text):
    now = time.localtime()
    ts = "%04d-%02d-%02d %02d:%02d:%02d" % (
        now.tm_year, now.tm_mon, now.tm_mday,
        now.tm_hour, now.tm_min, now.tm_sec)
    with open("nolticket_log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {text}\n")
    print(f"[{ts}] {text}")


# ────────────────────────────────────────────
#  GUI 전역 변수
# ────────────────────────────────────────────
app = None
win = None
e_id = e_pw = e_url = e_count = None
cb_standing_r = cb_standing_s = None
cb_jj_r = cb_jj_s = cb_jj_a = cb_jj_b = None
cb_allgrade = None
spin_interval = None
ch = None


# ────────────────────────────────────────────
#  ESC → 종료
# ────────────────────────────────────────────
def esc(event):
    if event.key() == QtCore.Qt.Key_Escape:
        log("프로그램 종료")
        sys.exit()
    event.accept()


# ────────────────────────────────────────────
#  유효성 검사 후 창 닫기
# ────────────────────────────────────────────
def on_start():
    if not e_id.text().strip():
        QMessageBox.warning(win, "오류", "아이디를 입력하세요.")
        return
    if not e_pw.text().strip():
        QMessageBox.warning(win, "오류", "비밀번호를 입력하세요.")
        return
    if not e_url.text().strip():
        QMessageBox.warning(win, "오류", "공연 URL을 입력하세요.")
        return
    win.close()
    ch.setText("True")


# ────────────────────────────────────────────
#  전체등급 체크박스 연동
# ────────────────────────────────────────────
def toggle_allgrade(state):
    checked = (state == Qt.Checked)
    for cb in [cb_standing_r, cb_standing_s, cb_jj_r, cb_jj_s, cb_jj_a, cb_jj_b]:
        cb.setChecked(checked)


# ────────────────────────────────────────────
#  GUI 구성
# ────────────────────────────────────────────
def build_gui():
    global app, win, e_id, e_pw, e_url, e_count
    global cb_standing_r, cb_standing_s, cb_jj_r, cb_jj_s, cb_jj_a, cb_jj_b, cb_allgrade
    global spin_interval, ch

    app = QApplication(sys.argv)
    win = QWidget()
    win.setWindowTitle("놀티켓 취소표 자동예매")
    win.setWindowIcon(QIcon())
    win.setFont(QFont("맑은 고딕", 10))
    win.keyPressEvent = esc

    # ── 로그인 정보
    grp_login = QGroupBox("로그인 정보")
    g1 = QFormLayout()
    e_id = QLineEdit()
    e_id.setPlaceholderText("놀티켓 아이디")
    e_pw = QLineEdit()
    e_pw.setEchoMode(QLineEdit.Password)
    e_pw.setPlaceholderText("비밀번호")
    g1.addRow("아이디", e_id)
    g1.addRow("비밀번호", e_pw)
    grp_login.setLayout(g1)

    # ── 공연 정보
    grp_show = QGroupBox("공연 정보")
    g2 = QFormLayout()
    e_url = QLineEdit()
    e_url.setPlaceholderText("예) https://www.nolticket.com/goods/XXXXX")
    e_count = QSpinBox()
    e_count.setRange(1, 4)
    e_count.setValue(1)
    g2.addRow("공연 URL", e_url)
    g2.addRow("예매 매수", e_count)
    grp_show.setLayout(g2)

    # ── 좌석 등급
    grp_seat = QGroupBox("좌석 등급 (복수 선택 가능)")
    gs = QVBoxLayout()

    cb_allgrade = QCheckBox("전체 등급")
    cb_allgrade.stateChanged.connect(toggle_allgrade)
    gs.addWidget(cb_allgrade)

    # 스탠딩
    row_standing = QHBoxLayout()
    lbl_standing = QLabel("스탠딩")
    lbl_standing.setFixedWidth(50)
    cb_standing_r = QCheckBox("R  (165,000원)")
    cb_standing_s = QCheckBox("S  (154,000원)")
    row_standing.addWidget(lbl_standing)
    row_standing.addWidget(cb_standing_r)
    row_standing.addWidget(cb_standing_s)
    row_standing.addStretch()
    gs.addLayout(row_standing)

    # 지정석
    row_jj = QHBoxLayout()
    lbl_jj = QLabel("지정석")
    lbl_jj.setFixedWidth(50)
    cb_jj_r = QCheckBox("R  (165,000원)")
    cb_jj_s = QCheckBox("S  (154,000원)")
    cb_jj_a = QCheckBox("A  (143,000원)")
    cb_jj_b = QCheckBox("B  (132,000원)")
    row_jj.addWidget(lbl_jj)
    row_jj.addWidget(cb_jj_r)
    row_jj.addWidget(cb_jj_s)
    row_jj.addWidget(cb_jj_a)
    row_jj.addWidget(cb_jj_b)
    row_jj.addStretch()
    gs.addLayout(row_jj)

    grp_seat.setLayout(gs)

    # ── 새로고침 간격
    grp_opt = QGroupBox("옵션")
    go = QFormLayout()
    spin_interval = QDoubleSpinBox()
    spin_interval.setRange(0.3, 10.0)
    spin_interval.setSingleStep(0.1)
    spin_interval.setValue(0.5)
    spin_interval.setSuffix(" 초")
    go.addRow("새로고침 간격", spin_interval)
    grp_opt.setLayout(go)

    # ── 시작 버튼
    btn_start = QPushButton("▶  예매 시작")
    btn_start.setFixedHeight(40)
    btn_start.setStyleSheet("background:#c0392b; color:white; font-weight:bold; font-size:13px;")
    btn_start.clicked.connect(on_start)

    ch = QLabel("False")

    # ── 전체 레이아웃
    vbox = QVBoxLayout()
    vbox.addWidget(grp_login)
    vbox.addWidget(grp_show)
    vbox.addWidget(grp_seat)
    vbox.addWidget(grp_opt)
    vbox.addWidget(btn_start)
    win.setLayout(vbox)
    win.setFixedWidth(420)
    win.show()
    app.exec_()


# ────────────────────────────────────────────
#  Selenium 드라이버 생성
# ────────────────────────────────────────────
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


# ────────────────────────────────────────────
#  놀티켓 로그인
# ────────────────────────────────────────────
def login(driver, user_id, user_pw):
    driver.get("https://www.nolticket.com/member/login")
    wait = WebDriverWait(driver, 15)

    wait.until(EC.presence_of_element_located((By.NAME, "m_id")))
    driver.find_element(By.NAME, "m_id").send_keys(user_id)
    driver.find_element(By.NAME, "m_pw").send_keys(user_pw)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']").click()

    time.sleep(2)
    if "login" in driver.current_url:
        raise Exception("로그인 실패 - 아이디/비밀번호를 확인하세요.")
    log("로그인 성공")


# grade_check 인덱스
# 0: 스탠딩R  1: 스탠딩S
# 2: 지정석R  3: 지정석S  4: 지정석A  5: 지정석B
GRADE_KEYWORDS = [
    ["스탠딩R", "스탠딩 R", "STANDING R"],
    ["스탠딩S", "스탠딩 S", "STANDING S"],
    ["지정석R", "지정석 R"],
    ["지정석S", "지정석 S"],
    ["지정석A", "지정석 A"],
    ["지정석B", "지정석 B"],
]


# ────────────────────────────────────────────
#  예매 진행
# ────────────────────────────────────────────
def book(driver, show_url, count, grade_check, interval):
    wait = WebDriverWait(driver, 10)
    attempt = 0

    log(f"취소표 감시 시작 → {show_url}")
    log(f"새로고침 간격: {interval}초 | 매수: {count}")

    while True:
        try:
            attempt += 1
            driver.get(show_url)
            time.sleep(interval)

            # 1) 예매 가능한 날짜/회차가 있는지 확인
            page = driver.page_source
            bs = BeautifulSoup(page, "html.parser")

            # 예매 불가 텍스트 감지
            sold_keywords = ["매진", "판매종료", "예매마감", "SOLD OUT"]
            body_text = bs.get_text()
            all_sold = all(kw in body_text for kw in ["매진"]) and \
                       not any(k not in body_text for k in sold_keywords)

            # 예매 가능 버튼 탐색
            book_btn = bs.select_one(
                "a.btn-book, button.btn-reserve, a[href*='reserve'], "
                ".btn-primary:not([disabled]), a.reserve-btn"
            )

            if book_btn is None:
                if attempt % 20 == 0:
                    log(f"[{attempt}회] 취소표 없음 - 계속 감시 중...")
                continue

            # 2) 예매 버튼 클릭
            href = book_btn.get("href", "")
            if href and href.startswith("http"):
                driver.get(href)
            else:
                driver.find_element(
                    By.CSS_SELECTOR,
                    "a.btn-book, button.btn-reserve, a[href*='reserve'], "
                    ".btn-primary, a.reserve-btn"
                ).click()

            time.sleep(1)
            log("예매 페이지 진입")

            # 3) 날짜/회차 선택 (가장 빠른 가능한 날짜)
            try:
                possible = driver.find_elements(
                    By.CSS_SELECTOR, "td.possible a, .schedule.possible, .date-possible"
                )
                if possible:
                    possible[0].click()
                    time.sleep(0.5)
                    log("날짜/회차 선택")
            except:
                pass

            # 4) 좌석 등급 선택
            try:
                for idx, flag in enumerate(grade_check):
                    if not flag:
                        continue
                    keywords = GRADE_KEYWORDS[idx]
                    grade_label = keywords[0]
                    selected = False

                    # 드롭다운 방식
                    try:
                        sel_el = driver.find_element(By.CSS_SELECTOR,
                            "select[name*='grade'], select[name*='price'], select[name*='class']")
                        sel = Select(sel_el)
                        for opt in sel.options:
                            if any(kw in opt.text for kw in keywords):
                                sel.select_by_visible_text(opt.text)
                                selected = True
                                break
                    except:
                        pass

                    # 버튼/라디오 방식
                    if not selected:
                        for kw in keywords:
                            btns = driver.find_elements(
                                By.XPATH,
                                f"//button[contains(text(),'{kw}')]"
                                f"|//label[contains(text(),'{kw}')]"
                                f"|//td[contains(text(),'{kw}')]"
                            )
                            if btns:
                                btns[0].click()
                                selected = True
                                break

                    if selected:
                        log(f"좌석 등급 선택: {grade_label}")
                        break
            except:
                pass

            # 5) 매수 선택
            try:
                count_sel = driver.find_elements(
                    By.CSS_SELECTOR, "select[name*='count'], select[name*='qty'], select[name*='num']"
                )
                if count_sel:
                    Select(count_sel[0]).select_by_value(str(count))
                    log(f"매수 선택: {count}매")
            except:
                pass

            # 6) 예매 확인 버튼
            try:
                confirm = wait.until(EC.element_to_be_clickable((
                    By.CSS_SELECTOR,
                    "button[type='submit'], input[type='submit'], "
                    "a.btn-confirm, button.btn-next, .btn-book-confirm"
                )))
                confirm.click()
                time.sleep(1)
                log("예매 확인 버튼 클릭")
            except:
                pass

            # 7) 결제 페이지 확인
            time.sleep(1)
            cur_url = driver.current_url
            if any(k in cur_url for k in ["payment", "pay", "order", "checkout", "결제"]):
                log("✅ 결제 페이지 도달 - 예매 성공!")

                # 결제 정보 저장
                with open("nolticket_result.txt", "w", encoding="utf-8") as f:
                    f.write(f"예매 성공\n")
                    f.write(f"URL: {cur_url}\n")
                    f.write(f"시각: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

                # 성공 알림창
                success_app = QApplication.instance()
                QMessageBox.information(None, "예매 성공!", "✅ 취소표 예매에 성공했습니다!\n결제 페이지를 확인하세요.")
                break
            else:
                log("결제 페이지 미도달 - 재시도")
                continue

        except KeyboardInterrupt:
            log("사용자가 중단했습니다.")
            break
        except Exception as ex:
            log(f"오류 발생: {ex}")
            time.sleep(1)
            continue


# ────────────────────────────────────────────
#  메인
# ────────────────────────────────────────────
if __name__ == '__main__':
    log("=== 놀티켓 취소표 자동예매 시작 ===")

    # GUI 실행
    build_gui()

    # 시작 안 누르고 닫은 경우
    if ch.text() == "False":
        log("프로그램 종료")
        sys.exit()

    # 입력값 수집
    user_id   = e_id.text().strip()
    user_pw   = e_pw.text().strip()
    show_url  = e_url.text().strip()
    count     = e_count.value()
    interval  = spin_interval.value()
    grade_check = [
        1 if cb_standing_r.isChecked() else 0,  # 스탠딩R
        1 if cb_standing_s.isChecked() else 0,  # 스탠딩S
        1 if cb_jj_r.isChecked()       else 0,  # 지정석R
        1 if cb_jj_s.isChecked()       else 0,  # 지정석S
        1 if cb_jj_a.isChecked()       else 0,  # 지정석A
        1 if cb_jj_b.isChecked()       else 0,  # 지정석B
    ]

    if not any(grade_check):
        QMessageBox.warning(None, "오류", "좌석 등급을 하나 이상 선택하세요.")
        sys.exit()

    # 드라이버 실행
    driver = None
    try:
        driver = make_driver()
        login(driver, user_id, user_pw)
        book(driver, show_url, count, grade_check, interval)

    except Exception as ex:
        log(f"치명적 오류: {ex}\n{traceback.format_exc()}")
        QMessageBox.critical(None, "오류", f"오류가 발생했습니다:\n{ex}")

    finally:
        if driver:
            input("엔터를 누르면 브라우저를 닫습니다...")
            driver.quit()
        log("=== 프로그램 종료 ===")
