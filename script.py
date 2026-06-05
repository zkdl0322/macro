# -*- encoding:utf8 -*-

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from urllib.request import urlretrieve
from PIL import Image
from PIL import ImageOps
import smtplib
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
import sys
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
from PyQt5 import QtGui, QtCore
import time
import traceback

# 개발자 : 박건희, 오수빈 (수정 : 박건희)

# test 파일 만드는 함수
def makeTest(testStr):
    test = open("test.html", "w", encoding="utf-8")
    test.write(testStr)
    test.close()

# 이미지를 선명하게 바꿔주는 함수
def cleanImage(imagePath):
    image = Image.open(imagePath)
    image = image.point(lambda x: 0 if x < 180 else 220)
    borderImage = ImageOps.expand(image, border=0, fill='white')
    borderImage.save(imagePath)
    borderImage.close()

# 활동로그를 기록하는 함수
def log(logText):
    now = time.localtime()
    nowTime = "%04d-%02d-%02d %02d:%02d:%02d" % (
        now.tm_year, now.tm_mon, now.tm_mday, now.tm_hour, now.tm_min, now.tm_sec)
    logFile = open("log.txt", "a", encoding="utf-8")
    logFile.write("[" + nowTime + "] " + str(logText) + "\n")
    logFile.close()

# 날짜 바꿀 때마다 선택된 날짜 정보 바꾸는 함수
def showDate():
    now = cal.selectedDate().toString()[2:]
    cal_lb.setText("<span style='color:#A90000'>선택된 날짜 : " + now[now.rindex(' ') + 1:] + "년 " + now[:now.index(' ')] + "월 "
            + now[now.index(' ') + 1:now.rindex(' ')] + "일</span>")

# 포커스 이동 함수
def nextFocus_1():
    e2.setFocus()
    e2.selectAll()
def nextFocus_2():
    e3.setFocus()
    e3.selectAll()
def nextFocus_3():
    e4.setFocus()
    e4.selectAll()
def nextFocus_4():
    cal.setFocus()
def nextFocus_5():
    e6.setFocus()
    e6.selectAll()
def nextFocus_6():
    e7.setFocus()
    e7.selectAll()
def nextFocus_7():
    cb1.setFocus()

# 사용자 정의 키보드 이벤트 : QWidget
def esc(event):
    if event.key() == QtCore.Qt.Key_Escape:
        log("프로그램 종료")
        sys.exit()
    event.accept()

# 사용자 입력창 닫아주는 함수
def close_1():
    if (str(e1.text()) == "") | (str(e2.text()) == "") | (str(e3.text()) == "") | (len(str(e3.text())) < 6) | (str(e4.text()) == "") | (str(e6.text()) == "회차") | (str(e7.text()) == "") | ((cb1.isChecked() | cb2.isChecked() | cb3.isChecked() | cb4.isChecked() | cb5.isChecked()) == False):
        if str(e1.text()) == "":
            msg("ID를 입력하십시오.")
            e1.setFocus()
        elif str(e2.text()) == "":
            msg("Password를 입력하십시오.")
            e2.setFocus()
        elif str(e3.text()) == "":
            msg("법정생년월일을 입력하십시오.")
            e3.setFocus()
        elif len(str(e3.text())) < 6:
            msg("법정생년월일을 전부 입력하십시오.")
            e3.setFocus()
        elif str(e4.text()) == "":
            msg("상품명을 입력하십시오.")
            e4.setFocus()
        elif str(e6.text()) == "회차":
            msg("회차를 입력하십시오.")
            e6.setFocus()
        elif str(e7.text()) == "":
            msg("할인을 입력하십시오.")
            e7.setFocus()
        elif cb1.isChecked() == False:
            msg("좌석등급을 선택하십시오.")
            cb1.setFocus()
    else:
        win.close()
        ch.setText("True")

# captcha 입력창 닫아주는 함수
def close_2():
    win.close()

# 경고창을 띄우는 함수
def msg(text):
    QMessageBox.information(win, "error!", text)

# main
if __name__ == '__main__':
    log("프로그램 시작")

    global e1, e2, e3, e4, cal, e6, e7, b1, ch, win
    global cb1, cb2, cb3, cb4, cb5

    app = QApplication(sys.argv)
    win = QWidget()
    win.keyPressEvent = esc

    # ID
    e1 = QLineEdit(win)
    e1.setPlaceholderText("ID를 입력해주세요")
    e1.setFocus()

    # pw
    e2 = QLineEdit(win)
    e2.setPlaceholderText("Password를 입력해주세요")
    e2.setEchoMode(QLineEdit.Password)

    # 주민등록번호
    e3 = QLineEdit(win)
    e3.setMaxLength(6)
    e3.setPlaceholderText("생년월일을 입력해주세요")
    e3.setValidator(QIntValidator())

    # 상품명
    e4 = QLineEdit(win)
    e4.setPlaceholderText("상품명을 입력해주세요")

    # 날짜 정보
    cal = QCalendarWidget(win)
    cal.showToday()
    now = time.localtime()
    cal.setMinimumDate(QDate(now.tm_year, now.tm_mon, now.tm_mday))
    cal.setGridVisible(True)
    cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
    cal.selectionChanged.connect(showDate)

    # 선택된 날짜 출력
    cal_lb = QLabel()
    cal_lb.setText("<span style='color:#A90000'>선택된 날짜 : " + str(now.tm_year) + "년 " + str(now.tm_mon) + "월 " + str(now.tm_mday) + "일</span>")
    cal_lb.setAlignment(Qt.AlignCenter)

    # 회차
    e6 = QLineEdit(win)
    e6.setInputMask('9회차')

    # 할인 정보
    e7 = QLineEdit(win)
    e7.setPlaceholderText("할인 유형을 입력해주세요")

    # 좌석 등급
    cb1 = QCheckBox("VIP", win)
    cb2 = QCheckBox("R", win)
    cb3 = QCheckBox("S", win)
    cb4 = QCheckBox("A", win)
    cb5 = QCheckBox("기타", win)

    e8 = QHBoxLayout()
    e8.addWidget(cb1)
    e8.addWidget(cb2)
    e8.addWidget(cb3)
    e8.addWidget(cb4)
    e8.addWidget(cb5)

    # 드롭박스 (무통장 은행)
    e9 = QComboBox(win)
    e9.addItems(["농협", "중앙", "국민", "우리", "기업", "씨티", "신한", "우체국", "하나"])

    # 시작버튼
    b1 = QPushButton("InterMacro Start", win)
    b1.toggle()
    b1.setAutoDefault(True)
    b1.clicked.connect(close_1)

    # 시작버튼 상태 변환용 라벨
    ch = QLabel("False")

    # enter 키로 포커스 이동하기
    e1.returnPressed.connect(nextFocus_1)
    e2.returnPressed.connect(nextFocus_2)
    e3.returnPressed.connect(nextFocus_3)
    e4.returnPressed.connect(nextFocus_4)
    cal.activated.connect(nextFocus_5)
    e6.returnPressed.connect(nextFocus_6)
    e7.returnPressed.connect(nextFocus_7)

    # Layout에 추가하기
    flo = QFormLayout()
    flo.addRow("ID", e1)
    flo.addRow("Password ", e2)
    flo.addRow("생년월일", e3)
    flo.addRow("상품명", e4)
    flo.addRow(cal_lb)
    flo.addRow(cal)
    flo.addRow("회차", e6)
    flo.addRow("할인 유형", e7)
    flo.addRow("좌석 등급", e8)
    flo.addRow("은행", e9)
    flo.addRow(b1)

    win.setLayout(flo)
    win.setWindowIcon(QIcon("interpark_icon.ico"))
    win.setGeometry(820, 350, 310, 300)
    win.setContentsMargins(3, 1, 3, 2)
    win.setWindowTitle("InterMacro")
    win.setFont(QFont("consolas"))
    win.show()

    app.exec_()

    if ch.text() == "False":
        log("프로그램 종료")
        sys.exit()
    else:
        log("사용자 입력받기 성공")

    # 입력한 정보 받아오기
    userID = e1.text().strip()
    userPW = e2.text().strip()
    userNum = e3.text()

    userSearch = e4.text().strip()
    selected_date = cal_lb.text()
    userTime = e6.text()
    userTicket = e7.text().strip()
    userBank = e9.currentText().strip()

    # 예매일 입력값 사용가능한 형태로 재배치
    userDate = selected_date[selected_date.index(": ") + 2:selected_date.index("년")]
    userDate = userDate + selected_date[selected_date.index("년") + 2:selected_date.index("월")].rjust(2, '0')
    userDate = userDate + selected_date[selected_date.index("월") + 2:selected_date.index("일")].rjust(2, '0')

    # 좌석 등급 체크여부 확인
    cbCheck = [0, 0, 0, 0, 0]
    if cb1.isChecked(): cbCheck[0] = 1
    if cb2.isChecked(): cbCheck[1] = 1
    if cb3.isChecked(): cbCheck[2] = 1
    if cb4.isChecked(): cbCheck[3] = 1
    if cb5.isChecked(): cbCheck[4] = 1

    # 은행 입력값 사용가능한 형태로 재배치
    if userBank.find("농협") != -1: userBank = 38052
    elif userBank.find("중앙") != -1: userBank = 38052
    elif userBank.find("국민") != -1: userBank = 38051
    elif userBank.find("우리") != -1: userBank = 38054
    elif userBank.find("기업") != -1: userBank = 38057
    elif userBank.find("씨티") != -1: userBank = 38055
    elif userBank.find("신한") != -1: userBank = 38056
    elif userBank.find("우체국") != -1: userBank = 38058
    elif userBank.find("하나") != -1: userBank = 38053
    else: userBank = 38051

    try:
        # 드라이브 객체 생성 (ChromeDriverManager로 자동 관리)
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))

        # 루트 1 : 링크로 입력했을 경우
        if userSearch.startswith('http://ticket.interpark.com/Ticket'):
            driver.get(userSearch)

        # 루트 2 : 링크가 아닌 타입일 경우
        else:
            driver.get("http://ticket.interpark.com/?smid1=header&smid2=ticket")

            driver.find_element(By.XPATH, "//div[@class='box']//input[@id='Nav_SearchWord']").send_keys(userSearch)
            driver.execute_script('Nav_Search(); return false;')

            try:
                alert = driver.switch_to.alert
                alert.accept()
            except:
                elem = ''

            log(userSearch + " 검색")

            # 예매하기_1
            if userSearch.find('공연예매권') == -1:
                infoIDX = 1
                while True:
                    if infoIDX == 1:
                        try:
                            info = driver.find_element(By.XPATH, '//*[@id="type1_list"]/div/div[2]/dl/dt/h4/a')
                        except:
                            info = driver.find_element(By.XPATH, '//*[@id="play_list"]/tr[1]/td[1]/div/dl/dt/h4/a')
                            infoIDX = 2
                    else:
                        info = driver.find_element(By.XPATH, '//*[@id="play_list"]/tr[' + str(infoIDX - 1) + ']/td[1]/div/dl/dt/h4/a')

                    if info.text.find('공연예매권') > -1:
                        infoIDX += 1
                        continue
                    else:
                        info.click()
                        break
            else:
                try:
                    driver.find_element(By.XPATH, '//*[@id="play_list"]/tr[1]/td[1]/div/dl/dt/h4/a').click()
                except:
                    driver.find_element(By.XPATH, '//*[@id="type1_list"]/div/div[2]/dl/dt/h4/a').click()

        # 공연 기간 정보 가져오기
        Dnow = driver.find_element(By.XPATH, '//p[@class="time"]').text
        Dnow = Dnow[Dnow.find('~ ') + 2:].replace('.', '')

        # 로그인
        driver.find_element(By.XPATH, '//*[@id="imgLogin"]').click()
        driver.find_element(By.NAME, 'UID').send_keys(userID)
        driver.find_element(By.NAME, 'PWD').send_keys(userPW)
        driver.execute_script("javascript:login();")
        log("로그인 성공")
        time.sleep(0.5)

        # 예매하기_2
        driver.execute_script('javascript:fnNormalBooking();')
        log("예매창 띄우기")
        driver.switch_to.window(driver.window_handles[1])

        try:
            driver.find_element(By.XPATH, "//img[@alt='일반회원 구매']").click()
            driver.switch_to.window(driver.window_handles[1])
        except:
            elem = ''

        try:
            elem = driver.find_element(By.XPATH, "//span[@class='btn02']")
            elem.click()
        except:
            elem = ''

        # 관람일/회차선택 (1단계)
        try:
            frame = driver.find_element(By.ID, 'ifrmBookStep')
            driver.switch_to.frame(frame)

            driver.execute_script("javascript: fnChangeMonth('" + userDate[:6] + "');")

            try:
                bs4 = BeautifulSoup(driver.page_source, "html.parser")
                calender = bs4.findAll('a', id='CellPlayDate')
                elem = calender[0]["onclick"]

                for i in range(0, len(calender)):
                    if "fnSelectPlayDate(" + str(i) + ", '" + userDate + "')" == calender[i]["onclick"]:
                        elem = calender[i]["onclick"]
                        break

                driver.execute_script("javascript:" + elem)

            except:
                driver.execute_script("javascript: fnChangeMonth('" + Dnow[:6] + "');")
                bs4 = BeautifulSoup(driver.page_source, "html.parser")
                calender = bs4.findAll('a', id='CellPlayDate')
                Dnow = calender[len(calender) - 1]["onclick"]
                driver.execute_script("javascript:" + Dnow)

            time.sleep(0.5)

            # 회차
            bs4 = BeautifulSoup(driver.page_source, "html.parser")
            timeList = bs4.find('div', class_='scrollY').find('span', id='TagPlaySeq').findAll('a', id='CellPlaySeq')

            try:
                if int(userTime[0]) <= len(timeList): elem = timeList[int(userTime[0]) - 1]["onclick"]
                else: elem = timeList[0]["onclick"]
            except:
                elem = timeList[0]["onclick"]

            driver.execute_script("javascript:" + elem)

            driver.switch_to.default_content()
            driver.execute_script("javascript:fnNextStep('P');")

            try:
                alert = driver.switch_to.alert
                alert.accept()
            except:
                elem = ''

            log("관람일/회차선택")
            time.sleep(0.5)

        except:
            elem = ''

        # 좌석 선택 (2단계)
        driver.switch_to.default_content()
        frame = driver.find_element(By.ID, 'ifrmSeat')
        driver.switch_to.frame(frame)

        # Captcha 뚫기 (QApplication은 이미 위에서 생성됨)
        try:
            while True:
                bs4 = BeautifulSoup(driver.page_source, "html.parser")
                Captcha = bs4.find('div', class_='capchaInner').find('img', id='imgCaptcha')['src']
                urlretrieve(Captcha, "captcha.jpg")
                cleanImage("captcha.jpg")

                # Captcha 입력창 (새 QDialog 사용)
                captcha_win = QDialog()
                captcha_win.setWindowTitle("captcha")
                captcha_win.setWindowIcon(QIcon("interpark_icon.ico"))
                captcha_win.setGeometry(830, 350, 200, 100)
                captcha_win.setContentsMargins(2, 1, 2, 2)
                captcha_win.setFont(QFont("consolas"))

                img = QLabel()
                img.setAlignment(Qt.AlignCenter)
                img.setPixmap(QPixmap("captcha.jpg"))

                captcha = QLineEdit(captcha_win)
                captcha.setFocus()
                captcha.setFont(QFont("consolas", 20))
                captcha.setAlignment(Qt.AlignCenter)
                captcha.editingFinished.connect(captcha_win.accept)

                b2 = QPushButton("입력완료", captcha_win)
                b2.setAutoDefault(True)
                b2.clicked.connect(captcha_win.accept)

                flo2 = QFormLayout()
                flo2.addRow(img)
                flo2.addRow(captcha)
                flo2.addRow(b2)
                captcha_win.setLayout(flo2)
                captcha_win.exec_()

                if captcha.text() == "": text = "ERROR"
                else: text = captcha.text()

                driver.find_element(By.XPATH, "//div[@class='validationTxt']//span").click()
                driver.find_element(By.XPATH, "//input[@id='txtCaptcha']").send_keys(text)
                driver.execute_script("javascript:fnCheck();")

                bs4 = BeautifulSoup(driver.page_source, "html.parser")
                Captcha_ch = bs4.find('div', class_='validationTxt alert')
                if Captcha_ch is None:
                    log("Captcha 입력 성공")
                    break
                else:
                    driver.execute_script("javascript:fnCapchaRefresh();")
                    continue
        except:
            elem = ''

        # 다양한 경우에 대한 빈 좌석 찾기
        driver.switch_to.default_content()
        frame = driver.find_element(By.ID, 'ifrmSeat')
        driver.switch_to.frame(frame)

        try:
            frame = driver.find_element(By.ID, 'ifrmSeatView')
            driver.switch_to.frame(frame)
            bs4 = BeautifulSoup(driver.page_source, "html.parser")
            elem = bs4.find('map')
        except:
            elem = None

        # 미니맵 = O, 구역 = O
        if elem is not None:
            areaList = bs4.findAll('area')

            seatch = False
            while seatch != True:
                for i in range(0, len(bs4.findAll('area')) + 1):
                    driver.switch_to.default_content()
                    frame = driver.find_element(By.ID, 'ifrmSeat')
                    driver.switch_to.frame(frame)
                    frame = driver.find_element(By.ID, 'ifrmSeatDetail')
                    driver.switch_to.frame(frame)

                    bs4 = BeautifulSoup(driver.page_source, "html.parser")
                    seatList = bs4.findAll('img', class_='stySeat')

                    try:
                        for i in range(0, len(seatList)):
                            seat = seatList[i]
                            text = seat['alt'][seat['alt'].find('[') + 1:]
                            if (text.find("VIP") != -1) & (cbCheck[0] == 1):
                                seatch = True
                                break
                            if (text.find("R") != -1) & (cbCheck[1] == 1):
                                seatch = True
                                break
                            if (text.find("S") != -1) & (cbCheck[2] == 1):
                                seatch = True
                                break
                            if (text.find("A") != -1) & (cbCheck[3] == 1):
                                seatch = True
                                break
                            if cbCheck[4] == 1:
                                seatch = True
                                break

                        if seatch == True:
                            driver.execute_script(seat['onclick'] + ";")
                            driver.switch_to.default_content()
                            frame = driver.find_element(By.ID, 'ifrmSeat')
                            driver.switch_to.frame(frame)
                            driver.execute_script("javascript:fnSelect();")
                            log("빈좌석 찾기 성공")
                            time.sleep(0.5)
                            break

                    except:
                        driver.switch_to.default_content()
                        frame = driver.find_element(By.ID, 'ifrmSeat')
                        driver.switch_to.frame(frame)
                        frame = driver.find_element(By.ID, 'ifrmSeatView')
                        driver.switch_to.frame(frame)

                        bs4 = BeautifulSoup(driver.page_source, "html.parser")
                        areaList = bs4.findAll('area')

                        if i == len(areaList):
                            driver.execute_script(areaList[0]["href"])
                        else:
                            try:
                                driver.execute_script(areaList[i]["href"])
                            except:
                                driver.execute_script(areaList[0]["href"])

                        time.sleep(0.5)

                        try:
                            alert = driver.switch_to.alert
                            alert.accept()
                            time.sleep(3)
                        except:
                            elem = ''

        else:
            try:
                driver.switch_to.default_content()
                frame = driver.find_element(By.ID, 'ifrmSeat')
                driver.switch_to.frame(frame)
                frame = driver.find_element(By.ID, 'ifrmSeatDetail')
                driver.switch_to.frame(frame)

                bs4 = BeautifulSoup(driver.page_source, "html.parser")

                # 미니맵 = X, 구역 = O
                if bs4.find('map') is not None:
                    areaList = bs4.findAll('area')

                    seatch = False
                    while seatch != True:
                        for i in range(0, len(areaList)):
                            driver.switch_to.default_content()
                            frame = driver.find_element(By.ID, 'ifrmSeat')
                            driver.switch_to.frame(frame)
                            frame = driver.find_element(By.ID, 'ifrmSeatDetail')
                            driver.switch_to.frame(frame)

                            driver.execute_script(areaList[i]["href"])

                            bs4 = BeautifulSoup(driver.page_source, "html.parser")
                            seatList = bs4.findAll('span', value='N')

                            try:
                                for i in range(0, len(seatList)):
                                    seat = seatList[i]
                                    text = seat['title'][seat['title'].find('[') + 1:]
                                    if (text.find("VIP") != -1) & (cbCheck[0] == 1):
                                        seatch = True
                                        break
                                    if (text.find("R") != -1) & (cbCheck[1] == 1):
                                        seatch = True
                                        break
                                    if (text.find("S") != -1) & (cbCheck[2] == 1):
                                        seatch = True
                                        break
                                    if (text.find("A") != -1) & (cbCheck[3] == 1):
                                        seatch = True
                                        break
                                    if cbCheck[4] == 1:
                                        seatch = True
                                        break

                                if seatch == True:
                                    driver.execute_script(seat['onclick'] + ";")
                                    driver.switch_to.default_content()
                                    frame = driver.find_element(By.ID, 'ifrmSeat')
                                    driver.switch_to.frame(frame)
                                    driver.execute_script("javascript:fnSelect();")
                                    log("빈좌석 찾기 성공")
                                    time.sleep(0.5)
                                    seatch = True
                                    break

                            except:
                                print("except_2")
                                driver.switch_to.default_content()
                                frame = driver.find_element(By.ID, 'ifrmSeat')
                                driver.switch_to.frame(frame)
                                driver.execute_script("javascript:fnSeatUpdate();")
                                time.sleep(0.5)

                                try:
                                    alert = driver.switch_to.alert
                                    alert.accept()
                                    time.sleep(3)
                                except:
                                    elem = ''

                # 미니맵 = X, 구역 = X
                else:
                    while True:
                        driver.switch_to.default_content()
                        frame = driver.find_element(By.ID, 'ifrmSeat')
                        driver.switch_to.frame(frame)
                        frame = driver.find_element(By.ID, 'ifrmSeatDetail')
                        driver.switch_to.frame(frame)

                        bs4 = BeautifulSoup(driver.page_source, "html.parser")
                        seatList = bs4.findAll('img', class_='stySeat')

                        try:
                            for i in range(0, len(seatList)):
                                seat = seatList[i]
                                text = seat['alt'][seat['alt'].find('[') + 1:]
                                print(text)
                                if (text.find("VIP") != -1) & (cbCheck[0] == 1):
                                    seatch = True
                                    break
                                if (text.find("R") != -1) & (cbCheck[1] == 1):
                                    seatch = True
                                    break
                                if (text.find("S") != -1) & (cbCheck[2] == 1):
                                    seatch = True
                                    break
                                if (text.find("A") != -1) & (cbCheck[3] == 1):
                                    seatch = True
                                    break
                                if cbCheck[4] == 1:
                                    seatch = True
                                    break

                            if seatch == True:
                                driver.find_element(By.XPATH, "//span[@title='" + seat['title'] + "']").click()
                                driver.switch_to.default_content()
                                frame = driver.find_element(By.ID, 'ifrmSeat')
                                driver.switch_to.frame(frame)
                                driver.execute_script("javascript:fnSelect();")
                                log("빈좌석 찾기 성공")
                                time.sleep(0.5)
                                break

                        except:
                            driver.switch_to.default_content()
                            frame = driver.find_element(By.ID, 'ifrmSeat')
                            driver.switch_to.frame(frame)
                            driver.execute_script("javascript:fnRefresh();")
                            time.sleep(0.5)

                            try:
                                alert = driver.switch_to.alert
                                alert.accept()
                                time.sleep(3)
                            except:
                                elem = ''
                            continue

            except:
                elem = ''

        # 가격/할인선택 (3단계)
        driver.switch_to.default_content()
        frame = driver.find_element(By.ID, 'ifrmBookStep')
        driver.switch_to.frame(frame)

        bs4 = BeautifulSoup(driver.page_source, "html.parser")
        ticketList = bs4.findAll('select')

        for i in range(0, len(ticketList)):
            ticketStr = ticketList[i]["pricegradename"]
            if ticketStr.find(userTicket) != -1:
                elem = ticketList[i]["index"]
                break

        try:
            driver.find_element(By.XPATH, "//td[@class='taL']//select[@index='" + str(elem) + "']//option[@value='1']").click()
        except:
            driver.find_element(By.XPATH, "//td[@class='taL']//select[@pricegrade='01']//option[@value='1']").click()

        driver.switch_to.default_content()
        driver.execute_script("javascript:fnNextStep('P');")

        try:
            alert = driver.switch_to.alert
            alert.accept()
        except:
            elem = ''

        log("가격/할인선택")
        time.sleep(0.5)

        # 배송선택/주문자확인 (4단계)
        frame = driver.find_element(By.ID, 'ifrmBookStep')
        driver.switch_to.frame(frame)

        driver.find_element(By.XPATH, "//td[@class='form']//input[@id='YYMMDD']").send_keys(userNum)

        bs4 = BeautifulSoup(driver.page_source, "html.parser")
        userEmail = bs4.find('input', id='Email')["value"]

        driver.switch_to.default_content()
        driver.execute_script("javascript:fnNextStep('P');")
        log("배송선택/주문자확인")
        time.sleep(0.5)

        # 결제하기_1 (5-1단계)
        frame = driver.find_element(By.ID, 'ifrmBookStep')
        driver.switch_to.frame(frame)

        elem = driver.find_element(By.XPATH, "//tr[@id='Payment_22004']//input[@name='Payment']")
        elem.click()

        elem = driver.find_element(By.XPATH, "//select[@id='BankCode']//option[@value='" + str(userBank) + "']")
        elem.click()

        driver.switch_to.default_content()
        driver.execute_script("javascript:fnNextStep('P');")
        log("결제하기")
        time.sleep(0.5)

        # 결제하기_2 (5-2단계)
        frame = driver.find_element(By.ID, 'ifrmBookStep')
        driver.switch_to.frame(frame)

        driver.find_element(By.XPATH, "//input[@id='CancelAgree']").click()
        driver.find_element(By.XPATH, "//input[@id='CancelAgree2']").click()

        driver.switch_to.default_content()
        driver.execute_script("javascript:fnNextStep('P');")
        log("예매 완료")
        time.sleep(0.5)

        # 예매 정보 출력
        driver.switch_to.default_content()
        frame = driver.find_element(By.ID, 'ifrmBookEnd')
        driver.switch_to.frame(frame)

        result = open("result.txt", "w", encoding="utf-8")

        result.write("___________ 상품정보 ___________\n")
        text_1 = driver.find_element(By.XPATH, "//p[@class='tit']//span[1]").text
        text_2 = driver.find_element(By.XPATH, "//p[@class='tit']//span[2]").text
        result.write(text_1 + " : " + text_2 + "\n")

        text_1 = driver.find_element(By.XPATH, "//div[@class='contT']//table//tbody//tr[1]//th").text
        text_2 = driver.find_element(By.XPATH, "//div[@class='contT']//table//tbody//tr[1]//td").text
        result.write(text_1 + " : " + text_2 + "\n")

        text_1 = driver.find_element(By.XPATH, "//div[@class='contT']//table//tbody//tr[2]//th").text
        text_2 = driver.find_element(By.XPATH, "//div[@class='contT']//table//tbody//tr[2]//td").text
        result.write(text_1 + " : " + text_2 + "\n")

        text_1 = driver.find_element(By.XPATH, "//div[@class='contT']//table//tbody//tr[3]//th").text
        text_2 = driver.find_element(By.XPATH, "//div[@class='contT']//table//tbody//tr[3]//td").text
        result.write(text_1 + " : " + text_2 + "\n")

        text_1 = driver.find_element(By.XPATH, "//div[@class='contT']//table//tbody//tr[4]//th").text
        text_2 = driver.find_element(By.XPATH, "//div[@class='contT']//table//tbody//tr[4]//td//div[@class='box_scroll']").text
        result.write(text_1 + " : " + text_2 + "\n")

        result.write("__________ 예매자 정보 __________\n")
        text_1 = driver.find_element(By.XPATH, "//div[@class='contB']//table//tbody//tr[1]//th").text
        text_2 = driver.find_element(By.XPATH, "//div[@class='contB']//table//tbody//tr[1]//td").text
        result.write(text_1 + " : " + text_2 + "\n")

        text_1 = driver.find_element(By.XPATH, "//div[@class='contB']//table//tbody//tr[2]//th").text
        text_2 = driver.find_element(By.XPATH, "//div[@class='contB']//table//tbody//tr[2]//td").text
        result.write(text_1 + " : " + text_2 + "\n")

        text_1 = driver.find_element(By.XPATH, "//div[@class='contB']//table//tbody//tr[3]//th").text
        text_2 = driver.find_element(By.XPATH, "//div[@class='contB']//table//tbody//tr[3]//td").text
        result.write(text_1 + " : " + text_2 + "\n")

        result.write("___________ 결제정보 ___________\n")
        text_1 = driver.find_element(By.XPATH, "//table[@class='new_t']//thead//tr[1]//th").text
        text_2 = driver.find_element(By.XPATH, "//table[@class='new_t']//thead//tr[1]//td").text
        result.write(text_1 + " : " + text_2 + "\n")

        text_1 = driver.find_element(By.XPATH, "//table[@class='new_t']//tbody//tr[1]//th").text
        text_2 = driver.find_element(By.XPATH, "//table[@class='new_t']//tbody//tr[1]//td").text
        result.write(text_1 + " : " + text_2 + "\n")

        text_1 = driver.find_element(By.XPATH, "//table[@class='new_t']//tbody//tr[2]//th").text
        text_2 = driver.find_element(By.XPATH, "//table[@class='new_t']//tbody//tr[2]//td").text
        result.write(text_1 + " : " + text_2 + "\n")

        text_1 = driver.find_element(By.XPATH, "//table[@class='new_t']//tbody//tr[3]//th").text
        text_2 = driver.find_element(By.XPATH, "//table[@class='new_t']//tbody//tr[3]//td").text
        result.write(text_1 + " : " + text_2 + "\n")

        text_1 = driver.find_element(By.XPATH, "//div[@class='completeL']//ul//li[1]").text
        result.write(text_1 + "\n")

        result.write("_________ 결제상세정보 _________\n")
        text_1 = driver.find_element(By.XPATH, "//div[@class='completeR']//table//tbody//tr[1]//th").text
        text_2 = driver.find_element(By.XPATH, "//div[@class='completeR']//table//tbody//tr[1]//td").text
        result.write(text_1 + " : " + text_2 + "\n")

        text_1 = driver.find_element(By.XPATH, "//div[@class='completeR']//table//tbody//tr[2]//th").text
        text_2 = driver.find_element(By.XPATH, "//div[@class='completeR']//table//tbody//tr[2]//td").text
        result.write(text_1 + " : " + text_2 + "\n")

        text_1 = driver.find_element(By.XPATH, "//div[@class='completeR']//table//tbody//tr[3]//th").text
        text_2 = driver.find_element(By.XPATH, "//div[@class='completeR']//table//tbody//tr[3]//td").text
        result.write(text_1 + " : " + text_2 + "\n")

        text_1 = driver.find_element(By.XPATH, "//div[@class='completeR']//table//tbody//tr[4]//th").text
        text_2 = driver.find_element(By.XPATH, "//div[@class='completeR']//table//tbody//tr[4]//td").text
        result.write(text_1 + " : " + text_2 + "\n")

        result.close()
        log("예매 정보 출력")

        # 예매창 닫기
        driver.close()
        log("예매창 닫기")

        # 마이페이지 접속
        driver.switch_to.window(driver.window_handles[0])
        driver.find_element(By.XPATH, '//li[@class="mypage"]/a').click()
        log("마이페이지 접속")

        # 예매결과 확인
        driver.execute_script("javascript: fnPlayBookDetail(0);")
        log("예매결과 확인")

    except Exception as ex:
        msg("error: " + str(ex))
        log("에러 발생: " + traceback.format_exc())

    log("프로그램 종료")
