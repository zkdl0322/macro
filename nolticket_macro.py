# -*- encoding:utf8 -*-

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from urllib.request import urlretrieve
from PIL import Image, ImageOps
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
#  이미지 선명하게 (캡차용)
# ────────────────────────────────────────────
def clean_image(path):
    img = Image.open(path)
    img = img.point(lambda x: 0 if x < 180 else 220)
    ImageOps.expand(img, border=0, fill='white').save(path)


# ────────────────────────────────────────────
#  GUI 전역 변수
# ────────────────────────────────────────────
app = None
win = None
e_url = e_count = None
cb_standing_r = cb_standing_s = None
cb_jj_r = cb_jj_s = cb_jj_a = cb_jj_b = None
cb_allgrade = None
spin_interval = None
ch = None

# grade_check 인덱스
# 0:스탠딩R  1:스탠딩S  2:지정석R  3:지정석S  4:지정석A  5:지정석B
GRADE_KEYWORDS = [
    ["스탠딩R", "스탠딩 R", "STANDING R"],
    ["스탠딩S", "스탠딩 S", "STANDING S"],
    ["지정석R", "지정석 R"],
    ["지정석S", "지정석 S"],
    ["지정석A", "지정석 A"],
    ["지정석B", "지정석 B"],
]


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
    global app, win, e_url, e_count
    global cb_standing_r, cb_standing_s, cb_jj_r, cb_jj_s, cb_jj_a, cb_jj_b, cb_allgrade
    global spin_interval, ch

    app = QApplication(sys.argv)
    win = QWidget()
    win.setWindowTitle("놀티켓 취소표 자동예매")
    win.setWindowIcon(QIcon())
    win.setFont(QFont("맑은 고딕", 10))
    win.keyPressEvent = esc

    # ── 로그인 안내
    grp_login = QGroupBox("로그인")
    g1 = QVBoxLayout()
    lbl_kakao = QLabel("※ 프로그램 시작 후 열리는 브라우저에서\n   카카오 로그인을 직접 진행해 주세요.")
    lbl_kakao.setStyleSheet("color:#555; font-size:10px;")
    g1.addWidget(lbl_kakao)
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

    # ── 옵션
    grp_opt = QGroupBox("옵션")
    go = QFormLayout()
    spin_interval = QDoubleSpinBox()
    spin_interval.setRange(5.0, 300.0)
    spin_interval.setSingleStep(5.0)
    spin_interval.setValue(30.0)
    spin_interval.setSuffix(" 초")
    go.addRow("새로고침 간격", spin_interval)
    grp_opt.setLayout(go)

    btn_start = QPushButton("▶  예매 시작")
    btn_start.setFixedHeight(40)
    btn_start.setStyleSheet("background:#c0392b; color:white; font-weight:bold; font-size:13px;")
    btn_start.clicked.connect(on_start)

    ch = QLabel("False")

    vbox = QVBoxLayout()
    vbox.addWidget(grp_login)
    vbox.addWidget(grp_show)
    vbox.addWidget(grp_seat)
    vbox.addWidget(grp_opt)
    vbox.addWidget(btn_start)
    win.setLayout(vbox)
    win.setFixedWidth(480)
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
#  놀티켓 카카오 로그인
# ────────────────────────────────────────────
def login(driver):
    driver.get("https://www.nolticket.com/member/login")
    wait = WebDriverWait(driver, 15)

    try:
        kakao_btn = wait.until(EC.element_to_be_clickable((
            By.CSS_SELECTOR,
            "a.kakao, a[href*='kakao'], button.kakao, img[alt*='카카오'], "
            "a[class*='kakao'], .sns-kakao, a[href*='SNS=K']"
        )))
        kakao_btn.click()
        log("카카오 로그인 버튼 클릭 - 브라우저에서 로그인 진행하세요")
    except Exception:
        log("카카오 버튼 자동 클릭 실패 - 브라우저에서 직접 카카오 로그인 해주세요")

    print("\n>>> 브라우저에서 카카오 로그인을 완료하면 자동으로 진행됩니다 <<<\n")
    original_window = driver.current_window_handle

    for _ in range(180):
        time.sleep(1)
        try:
            handles = driver.window_handles
            if original_window in handles:
                driver.switch_to.window(original_window)
            elif handles:
                driver.switch_to.window(handles[0])
        except:
            pass
        try:
            cur = driver.current_url
            if "login" not in cur and "member" not in cur:
                break
            if any(k in cur for k in ["mypage", "main", "index", "nolticket"]):
                if "login" not in cur:
                    break
        except:
            pass
    else:
        raise Exception("카카오 로그인 시간 초과 (3분)")

    try:
        driver.switch_to.window(driver.window_handles[0])
    except:
        pass

    log("카카오 로그인 성공")


# ────────────────────────────────────────────
#  놀티켓: 잔여석 감시 → 예매하기 클릭
# ────────────────────────────────────────────
def watch_nolticket(driver, show_url, grade_check, interval):
    attempt = 0
    log(f"취소표 감시 시작 → {show_url}")

    while True:
        attempt += 1
        try:
            driver.get(show_url)
            time.sleep(interval)

            bs = BeautifulSoup(driver.page_source, "html.parser")
            body = bs.get_text()

            # 잔여석 있는지 확인 (0석이 아닌 등급 탐색)
            found_grade = None
            for idx, flag in enumerate(grade_check):
                if not flag:
                    continue
                for kw in GRADE_KEYWORDS[idx]:
                    # "스탠딩R 0석" 패턴 → 0석이면 패스
                    import re
                    pattern = re.compile(kw + r'[^\d]*(\d+)석')
                    m = pattern.search(body)
                    if m and int(m.group(1)) > 0:
                        found_grade = kw
                        break
                if found_grade:
                    break

            if found_grade is None:
                if attempt % 5 == 0:
                    log(f"[{attempt}회] 잔여석 없음 - 계속 감시 중...")
                continue

            log(f"✅ 잔여석 발견! 등급: {found_grade} → 예매하기 클릭")

            # 예매하기 버튼 클릭
            try:
                book_btn = driver.find_element(
                    By.CSS_SELECTOR,
                    "button.btn-reserve, a.btn-reserve, "
                    "button.reserve, a.reserve, "
                    ".booking-btn, button[class*='book']"
                )
                book_btn.click()
            except:
                # 텍스트로 탐색
                btns = driver.find_elements(By.XPATH, "//button[contains(text(),'예매')] | //a[contains(text(),'예매하기')]")
                if btns:
                    btns[0].click()
                else:
                    log("예매하기 버튼을 찾지 못했습니다 - 재시도")
                    continue

            time.sleep(2)

            # 인터파크로 넘어갔는지 확인
            # 새 탭이 열릴 수 있음
            if len(driver.window_handles) > 1:
                driver.switch_to.window(driver.window_handles[-1])
                time.sleep(1)

            cur_url = driver.current_url
            if "interpark" in cur_url or "poticket" in cur_url:
                log(f"인터파크 예매 페이지로 이동: {cur_url}")
                return  # 인터파크 처리로 넘김
            else:
                log(f"예매 페이지 이동 실패 ({cur_url}) - 재시도")
                continue

        except KeyboardInterrupt:
            raise
        except Exception as ex:
            log(f"감시 오류: {ex}")
            time.sleep(2)
            continue


# ────────────────────────────────────────────
#  캡차 입력창 (PyQt5 Dialog)
# ────────────────────────────────────────────
def ask_captcha(img_path):
    dialog = QDialog()
    dialog.setWindowTitle("캡차 입력")
    dialog.setFont(QFont("맑은 고딕", 11))
    dialog.setFixedWidth(320)

    img_label = QLabel()
    img_label.setAlignment(Qt.AlignCenter)
    img_label.setPixmap(QPixmap(img_path))

    captcha_input = QLineEdit()
    captcha_input.setFont(QFont("Consolas", 18))
    captcha_input.setAlignment(Qt.AlignCenter)
    captcha_input.setPlaceholderText("문자를 입력하세요")

    btn_ok = QPushButton("입력완료")
    btn_ok.setFixedHeight(36)
    btn_ok.setStyleSheet("background:#2c3e50; color:white; font-weight:bold;")
    btn_ok.clicked.connect(dialog.accept)
    captcha_input.returnPressed.connect(dialog.accept)

    layout = QVBoxLayout()
    layout.addWidget(img_label)
    layout.addWidget(captcha_input)
    layout.addWidget(btn_ok)
    dialog.setLayout(layout)
    dialog.exec_()

    return captcha_input.text().strip()


# ────────────────────────────────────────────
#  인터파크: 캡차 → 좌석선택 → 결제
# ────────────────────────────────────────────
def book_interpark(driver, count, grade_check):
    wait = WebDriverWait(driver, 15)
    log("인터파크 예매 진행 시작")

    # ── 캡차 처리
    try:
        # 캡차 iframe으로 진입
        try:
            frame = driver.find_element(By.ID, "ifrmSeat")
            driver.switch_to.frame(frame)
        except:
            pass

        for _ in range(10):
            bs = BeautifulSoup(driver.page_source, "html.parser")
            captcha_img = bs.find("img", id="imgCaptcha")
            if captcha_img is None:
                break

            img_src = captcha_img.get("src", "")
            if img_src:
                urlretrieve(img_src, "captcha.jpg")
                clean_image("captcha.jpg")

            # 캡차 입력창 띄우기
            driver.switch_to.default_content()
            captcha_text = ask_captcha("captcha.jpg")

            try:
                frame = driver.find_element(By.ID, "ifrmSeat")
                driver.switch_to.frame(frame)
            except:
                pass

            if not captcha_text:
                captcha_text = "ERROR"

            try:
                driver.find_element(By.XPATH, "//div[@class='validationTxt']//span").click()
                driver.find_element(By.ID, "txtCaptcha").send_keys(captcha_text)
                driver.execute_script("javascript:fnCheck();")
                time.sleep(0.5)
            except:
                pass

            bs2 = BeautifulSoup(driver.page_source, "html.parser")
            if bs2.find("div", class_="validationTxt alert") is None:
                log("캡차 통과")
                break
            else:
                log("캡차 실패 - 재시도")
                try:
                    driver.execute_script("javascript:fnCapchaRefresh();")
                except:
                    pass

        driver.switch_to.default_content()

    except Exception as ex:
        log(f"캡차 처리 중 오류 (계속 진행): {ex}")
        driver.switch_to.default_content()

    # ── 좌석 선택
    try:
        frame = driver.find_element(By.ID, "ifrmSeat")
        driver.switch_to.frame(frame)
    except:
        pass

    seat_found = False
    for _ in range(30):  # 최대 30회 재시도
        try:
            bs = BeautifulSoup(driver.page_source, "html.parser")

            # 선택 가능한 좌석 탐색
            seat_list = bs.findAll("img", class_="stySeat")
            if not seat_list:
                seat_list = bs.findAll("span", value="N")

            for seat in seat_list:
                seat_text = (seat.get("alt") or seat.get("title") or "").upper()
                for idx, flag in enumerate(grade_check):
                    if not flag:
                        continue
                    for kw in GRADE_KEYWORDS[idx]:
                        if kw.upper() in seat_text:
                            # 좌석 클릭
                            try:
                                onclick = seat.get("onclick", "")
                                if onclick:
                                    driver.execute_script(onclick + ";")
                                else:
                                    title = seat.get("title", "")
                                    driver.find_element(
                                        By.XPATH, f"//span[@title='{title}']"
                                    ).click()
                            except:
                                pass
                            log(f"좌석 선택: {seat_text[:30]}")
                            seat_found = True
                            break
                    if seat_found:
                        break
            if seat_found:
                break

        except:
            pass

        time.sleep(0.5)

        # 구역 미니맵 클릭 시도
        try:
            areas = driver.find_elements(By.TAG_NAME, "area")
            if areas:
                driver.execute_script(areas[0].get_attribute("href") or "")
                time.sleep(0.5)
        except:
            pass

        try:
            driver.execute_script("javascript:fnRefresh();")
            time.sleep(0.5)
        except:
            pass

    driver.switch_to.default_content()

    if not seat_found:
        log("좌석을 찾지 못했습니다.")

    # ── 좌석선택완료 버튼
    try:
        frame = driver.find_element(By.ID, "ifrmSeat")
        driver.switch_to.frame(frame)
        driver.execute_script("javascript:fnSelect();")
        driver.switch_to.default_content()
        log("좌석선택완료")
        time.sleep(0.5)
    except:
        driver.switch_to.default_content()

    # ── 가격/할인 선택 (3단계)
    try:
        frame = driver.find_element(By.ID, "ifrmBookStep")
        driver.switch_to.frame(frame)

        bs = BeautifulSoup(driver.page_source, "html.parser")
        ticket_list = bs.findAll("select")
        elem_idx = None
        for t in ticket_list:
            for idx, flag in enumerate(grade_check):
                if not flag:
                    continue
                for kw in GRADE_KEYWORDS[idx]:
                    if kw in t.get("pricegradename", ""):
                        elem_idx = t.get("index")
                        break
                if elem_idx:
                    break
            if elem_idx:
                break

        try:
            if elem_idx:
                driver.find_element(
                    By.XPATH,
                    f"//td[@class='taL']//select[@index='{elem_idx}']//option[@value='1']"
                ).click()
            else:
                driver.find_element(
                    By.XPATH,
                    "//td[@class='taL']//select[@pricegrade='01']//option[@value='1']"
                ).click()
        except:
            pass

        driver.switch_to.default_content()
        driver.execute_script("javascript:fnNextStep('P');")
        log("가격/할인 선택")
        time.sleep(0.5)

    except:
        driver.switch_to.default_content()

    # ── 결제 페이지 도달 확인
    time.sleep(1)
    cur_url = driver.current_url
    if any(k in cur_url for k in ["payment", "pay", "order", "checkout", "BookEnd", "완료"]):
        log("✅ 예매 성공! 결제 페이지 도달")
        with open("nolticket_result.txt", "w", encoding="utf-8") as f:
            f.write(f"예매 성공\nURL: {cur_url}\n시각: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        QMessageBox.information(None, "예매 성공! 🎉",
            "✅ 취소표 예매에 성공했습니다!\n브라우저에서 결제를 완료해 주세요.")
        return True

    log(f"결제 페이지 미도달 ({cur_url})")
    return False


# ────────────────────────────────────────────
#  메인 루프
# ────────────────────────────────────────────
def run(driver, show_url, count, grade_check, interval):
    while True:
        try:
            # 1) 놀티켓 감시
            watch_nolticket(driver, show_url, grade_check, interval)

            # 2) 인터파크 예매
            success = book_interpark(driver, count, grade_check)
            if success:
                break

            log("예매 실패 - 처음부터 재시도")
            time.sleep(2)

        except KeyboardInterrupt:
            log("사용자가 중단했습니다.")
            break
        except Exception as ex:
            log(f"오류 발생: {ex}\n{traceback.format_exc()}")
            time.sleep(2)
            continue


# ────────────────────────────────────────────
#  메인
# ────────────────────────────────────────────
if __name__ == '__main__':
    log("=== 놀티켓 취소표 자동예매 시작 ===")

    build_gui()

    if ch.text() == "False":
        log("프로그램 종료")
        sys.exit()

    show_url  = e_url.text().strip()
    count     = e_count.value()
    interval  = spin_interval.value()
    grade_check = [
        1 if cb_standing_r.isChecked() else 0,
        1 if cb_standing_s.isChecked() else 0,
        1 if cb_jj_r.isChecked()       else 0,
        1 if cb_jj_s.isChecked()       else 0,
        1 if cb_jj_a.isChecked()       else 0,
        1 if cb_jj_b.isChecked()       else 0,
    ]

    if not any(grade_check):
        QMessageBox.warning(None, "오류", "좌석 등급을 하나 이상 선택하세요.")
        sys.exit()

    driver = None
    try:
        driver = make_driver()
        login(driver)
        run(driver, show_url, count, grade_check, interval)

    except Exception as ex:
        log(f"치명적 오류: {ex}\n{traceback.format_exc()}")
        QMessageBox.critical(None, "오류", f"오류가 발생했습니다:\n{ex}")

    finally:
        if driver:
            input("\n엔터를 누르면 브라우저를 닫습니다...")
            driver.quit()
        log("=== 프로그램 종료 ===")
