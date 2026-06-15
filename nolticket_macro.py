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
GRADES = ["스탠딩R", "스탠딩S", "지정석R", "지정석S", "지정석A", "지정석B"]  # fallback only

# ── KSPO DOME 좌석 배치 ──────────────────────────
# 각 구역은 3자리 코드(101~115, 224~243)로 식별됨
#  - 스탠딩(FLOOR): 가(001) 나(002) 다(003) 라(004)
#  - 지정석 1F: 101~115 (총 15구역)
#  - 지정석 2F: 224~243 (총 20구역)
KSPO_DOME = {
    "grades": ["스탠딩", "지정석 1F", "지정석 2F"],
    "zones": {
        "스탠딩": [
            "가(001)", "나(002)", "다(003)", "라(004)"
        ],
        "지정석 1F": [
            "101구역", "102구역", "103구역", "104구역", "105구역",
            "106구역", "107구역", "108구역", "109구역", "110구역",
            "111구역", "112구역", "113구역", "114구역", "115구역",
        ],
        "지정석 2F": [
            "224구역", "225구역", "226구역", "227구역", "228구역",
            "229구역", "230구역", "231구역", "232구역", "233구역",
            "234구역", "235구역", "236구역", "237구역", "238구역",
            "239구역", "240구역", "241구역", "242구역", "243구역",
        ],
    },
}


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
    # nol.yanolja.com 만 로그인 완료로 인식
    def _is_logged_in(self):
        url = self._url()
        return "nol.yanolja.com" in url

    # ── 캡챠 입력창 요소 찾기 (iframe 포함) ──
    # 캡챠 전용 placeholder만 엄격하게 매칭 (다른 입력창 오인 방지)
    def _find_captcha_input(self):
        drv = self.driver
        input_sels = [
            "input[placeholder*='문자를 입력해주세요']",
            ".captcha_input input",
            "#captchaInput",
        ]
        # 1) 현재 컨텍스트에서 탐색
        for sel in input_sels:
            try:
                el = drv.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed(): return el
            except: pass
        # 2) 모든 iframe 시도
        try:
            frames = drv.find_elements(By.TAG_NAME, "iframe")
        except: frames = []
        for frame in frames:
            try:
                drv.switch_to.frame(frame)
                for sel in input_sels:
                    try:
                        el = drv.find_element(By.CSS_SELECTOR, sel)
                        if el.is_displayed(): return el
                    except: pass
                drv.switch_to.default_content()
            except:
                drv.switch_to.default_content()
        return None

    # ── 안심예매 캡챠 팝업 감지 ────────────────
    # 캡챠 전용 입력창(문자를 입력해주세요)이 실제로 화면에 보일 때만 True
    def _captcha_visible(self):
        drv = self.driver
        try:
            drv.switch_to.default_content()
            return self._find_captcha_input() is not None
        except:
            return False

    # ── 안심예매 캡챠 처리 ────────────────────
    def _handle_captcha(self):
        drv = self.driver

        for attempt in range(10):
            drv.switch_to.default_content()
            if not self._captcha_visible():
                self.log("→ 캡챠 통과"); return True

            self.log("보안 문자를 입력해주세요. 없을 경우, 0을 입력해주세요 →")
            ans = self._ask(timeout=90)
            if ans is None:
                self.log("입력 시간 초과"); return False
            self.log(f"→ {ans}")

            if ans.strip() == "0":
                return True

            try:
                drv.switch_to.default_content()
                inp = self._find_captcha_input()
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
                    "//button[contains(text(),'확인')]",
                    "//input[@type='submit']",
                ]:
                    try:
                        btn = drv.find_element(By.XPATH, bsel)
                        if btn.is_displayed():
                            drv.execute_script("arguments[0].click();", btn)
                            confirmed = True; break
                    except: pass

                if not confirmed:
                    for bsel in [".btn_ok", ".btn_confirm", "button.confirm",
                                 "button[type='submit']"]:
                        try:
                            el = drv.find_element(By.CSS_SELECTOR, bsel)
                            if el.is_displayed():
                                drv.execute_script("arguments[0].click();", el)
                                confirmed = True; break
                        except: pass

                drv.switch_to.default_content()
                self._wait(2.0)  # 제출 후 충분히 대기

            except Exception as e:
                self.log(f"캡챠 처리 오류: {e}")
                drv.switch_to.default_content()
                continue

            drv.switch_to.default_content()
            if not self._captcha_visible():
                self.log("→ 캡챠 통과"); return True

            self.log(f"캡챠 재시도 ({attempt+1}/10)")

        return False

    # ── 좌석 등급 선택 (KSPO DOME 고정) ─────
    def _ask_grade(self):
        grade_list = KSPO_DOME["grades"]
        self.log("좌석 등급을 입력해주세요:")
        self.log("1. 모두")
        for i, g in enumerate(grade_list, 2):
            self.log(f"{i}. {g}")
        ans = self._ask(timeout=120)
        if ans is None:
            self.log("시간 초과 → 모두로 진행"); return 0, grade_list
        self.log(f"→ {ans}")
        try: n = int(ans)
        except: return 0, grade_list
        if n == 1: return 0, grade_list
        if 2 <= n <= len(grade_list) + 1: return n - 1, grade_list
        return 0, grade_list

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

    # ── 구역 선택 (KSPO DOME 고정) ───────────
    def _ask_zones(self, grade_idx, grade_list=None):
        gl = grade_list or KSPO_DOME["grades"]
        if grade_idx >= 1 and grade_idx <= len(gl):
            grade_name = gl[grade_idx - 1]
            zone_list  = KSPO_DOME["zones"].get(grade_name, [])
        else:
            # 모두 선택 → 전체 구역 합산
            zone_list = []
            for zl in KSPO_DOME["zones"].values():
                zone_list.extend(zl)

        for i, z in enumerate(zone_list, 1):
            self.log(f"{i}. {z}")
        self.log("구역을 번호로 입력해주세요. ','로 구분하여 여러개 입력 가능합니다.")
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
    def _click_seat(self, grade_idx, grade_list=None):
        drv = self.driver
        # motickets: 회색(매진)이 아닌 색깔 있는 좌석만 클릭
        # 회색 계열 fill: #ccc, #999, #aaa, #bbb, #ddd, #eee, gray, #c8c8c8 등
        js = r"""
        var GRAY = /^(#[89a-f][0-9a-f]{2}|#[c-f]{1}[0-9a-f]{2}|gray|grey|#c[0-9a-f]{4}|#d[0-9a-f]{4}|#e[0-9a-f]{4}|#f0f0f0|#eeeeee|#dddddd|#cccccc|#bbbbbb|#aaaaaa|#999999)/i;
        function isSoldByColor(el){
            var fill = el.getAttribute('fill') || el.style.fill || '';
            if (fill && GRAY.test(fill.trim())) return true;
            // computed style
            try {
                var cs = window.getComputedStyle(el);
                var cf = cs.fill || '';
                // rgb(170,170,170) 계열 → 채도 낮으면 매진
                var m = cf.match(/rgb\s*\(\s*(\d+),\s*(\d+),\s*(\d+)/);
                if (m) {
                    var r=+m[1], g=+m[2], b=+m[3];
                    var diff = Math.max(r,g,b) - Math.min(r,g,b);
                    if (diff < 25 && r > 140) return true; // 회색 계열
                }
            } catch(e){}
            return false;
        }
        function isSoldByClass(el){
            var c = (el.className && el.className.baseVal!==undefined)
                    ? el.className.baseVal : (el.className||'');
            c = (''+c).toLowerCase();
            return (c.indexOf('sold')>=0 || c.indexOf('disable')>=0 ||
                    c.indexOf('reserved')>=0 || c.indexOf('unavailab')>=0 ||
                    c.indexOf('closed')>=0 || c.indexOf('none')>=0);
        }
        // SVG 좌석(rect, circle, path, use)만 탐색
        var seats = document.querySelectorAll(
            'rect[fill], circle[fill], path[fill], ' +
            'rect[class], circle[class], use[href], use[xlink\\:href]');
        var cands = [];
        for (var i = 0; i < seats.length; i++) {
            var el = seats[i];
            if (isSoldByClass(el)) continue;
            if (isSoldByColor(el)) continue;
            if (el.getAttribute('aria-disabled') === 'true') continue;
            var r = el.getBoundingClientRect ? el.getBoundingClientRect() : null;
            if (!r || r.width < 3 || r.height < 3) continue;
            cands.push(el);
        }
        if (cands.length === 0) return 0;
        // SVG 요소는 .click()이 없으므로 dispatchEvent 사용
        var el = cands[0];
        try { el.click(); } catch(e) {
            el.dispatchEvent(new MouseEvent('click',
                {bubbles:true, cancelable:true, view:window}));
        }
        return cands.length;
        """
        try:
            n = drv.execute_script(js)
            if n and n > 0:
                self.log(f"예매 가능 좌석 발견 → 클릭 (후보 {n}개)")
                self._wait(1.0)
                # 클릭 후 URL/팝업 변화가 없으면 실패로 처리
                after_url = self._url()
                if self._on_detail_page() and "select" not in after_url:
                    # 좌석 선택 확인 팝업이나 URL 변화 기다리기
                    for _ in range(8):
                        self._wait(0.5)
                        new_url = self._url()
                        if new_url != after_url or not self._on_detail_page():
                            return True
                    # URL 변화 없으면 좌석 선택 안 된 것 → False
                    return False
                return True
        except Exception as e:
            self.log(f"좌석 클릭 오류: {e}")
        return False

    # ── 퍼즐 슬라이더 ─────────────────────────
    def _solve_puzzle(self):
        drv = self.driver
        found = False
        for sel in [".slider_wrap",".puzzle_wrap","[class*='slider']","[class*='puzzle']"]:
            try:
                if drv.find_element(By.CSS_SELECTOR, sel).is_displayed():
                    found = True; break
            except: pass
        if not found:
            try: found = "슬라이더를 밀어" in drv.page_source
            except: pass
        if not found: return

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
        self.log(f"[퍼즐 감지] 목표 위치: {offset}px")
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

    # ── 구역 클릭 (iframe area 태그 + JS 겸용) ──
    def _click_zone(self, zone_num):
        drv = self.driver
        # 1) BookMain.asp (iframe) - area 태그로 클릭
        try:
            drv.switch_to.default_content()
            self._to_frame("ifrmSeat", "mainFrame")
            for area in drv.find_elements(By.TAG_NAME, "area"):
                t = (area.get_attribute("title") or
                     area.get_attribute("alt") or "").strip()
                if t == zone_num or t == zone_num + "구역" or t == zone_num + "영역":
                    drv.execute_script("arguments[0].click();", area)
                    drv.switch_to.default_content()
                    return True
            # href 방식
            for area in drv.find_elements(By.TAG_NAME, "area"):
                href = area.get_attribute("href") or ""
                if zone_num in href:
                    drv.execute_script(href.replace("javascript:", ""))
                    drv.switch_to.default_content()
                    return True
            drv.switch_to.default_content()
        except:
            try: drv.switch_to.default_content()
            except: pass

        # 2) motickets (SPA) - JS 텍스트/속성 검색
        js = r"""
        var target = arguments[0];
        function tryClick(el){
            for (var d=0; d<6 && el; d++){
                var tag = (el.tagName||'').toLowerCase();
                if (tag==='a' || tag==='button' || el.onclick ||
                    el.getAttribute('role')==='button' ||
                    (el.style && el.style.cursor==='pointer')){
                    el.click(); return true;
                }
                el = el.parentElement;
            }
            return false;
        }
        var nodes = document.querySelectorAll('text,tspan,a,g,span,div,li,button,path');
        for (var i=0;i<nodes.length;i++){
            var txt=(nodes[i].textContent||'').trim();
            if(txt===target||txt===target+'구역'||txt===target+'영역'){
                if(tryClick(nodes[i])) return true;
            }
        }
        var attrs=document.querySelectorAll('[title],[data-zone],[data-area],[aria-label]');
        for(var i=0;i<attrs.length;i++){
            var t=(attrs[i].getAttribute('title')||attrs[i].getAttribute('data-zone')||
                   attrs[i].getAttribute('data-area')||attrs[i].getAttribute('aria-label')||'');
            if(t.trim()===target||t===target+'구역'||t===target+'영역'){
                if(tryClick(attrs[i])) return true;
            }
        }
        return false;
        """
        try:
            return bool(drv.execute_script(js, zone_num))
        except:
            return False

    # ── 구역 순회 ─────────────────────────────
    def _rotate_zones(self, zones, grade_idx, grade_list=None):
        cycle = 0
        consecutive_err = 0
        self.log(f"구역 순회를 시작합니다 (딜레이 {self.delay}초)")
        while True:
            for zone in zones:
                self._wait(0)
                # 브라우저 세션 생존 확인
                try:
                    _ = self.driver.current_url
                except Exception:
                    self.log("브라우저가 종료되어 순회를 중단합니다."); return

                try:
                    # 구역번호 정규화: "가(001)"→"001", "206영역"→"206", "105구역"→"105"
                    zone_num = zone.replace("구역", "").replace("영역", "").strip()
                    if "(" in zone_num:
                        zone_num = zone_num.split("(")[-1].replace(")", "").strip()

                    # 구역 클릭 (실패해도 다음 구역으로)
                    if not self._click_zone(zone_num):
                        continue

                    self._wait(self.delay)
                    self._solve_puzzle()

                    # 예매 가능 좌석 클릭 → 성공하면 순회 종료
                    if self._click_seat(grade_idx, grade_list):
                        return
                    consecutive_err = 0

                except InterruptedError:
                    raise
                except Exception as e:
                    consecutive_err += 1
                    self.log(f"구역 오류(건너뜀): {str(e)[:60]}")
                    if consecutive_err >= 15:
                        self.log("오류가 계속되어 순회를 중단합니다."); return
                    self._wait(0.5)
            cycle += 1
            if cycle % 5 == 0:
                self.log(f"구역 순회 {cycle}바퀴 완료...")

    # ── 좌석선택완료 / 다음단계 ───────────────
    def _click_complete(self):
        drv = self.driver
        self.log("좌석선택완료 클릭")
        for xp in [
            "//a[contains(text(),'좌석선택완료')]",
            "//button[contains(text(),'좌석선택완료')]",
            "//button[contains(text(),'선택완료')]",
            "//button[contains(text(),'다음')]",
            "//a[contains(text(),'다음')]",
            "//button[contains(text(),'선택완료')]",
        ]:
            try:
                btn = drv.find_element(By.XPATH, xp)
                if btn.is_displayed():
                    drv.execute_script("arguments[0].click();", btn)
                    break
            except: pass
        self._wait(1.5)

    # ── 결제 페이지 감지 ──────────────────────
    # motickets: step3 이상 URL 또는 결제 전용 페이지로 이동했을 때만 감지
    def _is_payment_page(self):
        try:
            url = self.driver.current_url
            # motickets 결제 단계: step3, payment, checkout, order 등
            pay_url_kw = ["step3", "payment", "checkout", "order", "BookEnd",
                          "poticket", "pay/"]
            if any(k in url for k in pay_url_kw):
                return True
            # step2는 절대 결제 페이지 아님
            if "step2" in url:
                return False
            # step2 아닌 다른 URL로 이동했고 결제 키워드가 소스에 있을 때
            src = self.driver.page_source
            pay_src_kw = ["주문금액", "결제수단", "최종결제금액", "결제하기"]
            return any(k in src for k in pay_src_kw)
        except:
            return False

    # ── 결제 대기 ─────────────────────────────
    def _wait_payment(self):
        self.log("취소표를 잡았습니다! 결제 페이지 대기 중 - 소리 알림 시작")

        def _beep_loop(stop_ev):
            while not stop_ev.is_set():
                try:
                    winsound.Beep(1000, 400)
                    time.sleep(0.15)
                    winsound.Beep(1300, 400)
                    time.sleep(0.5)
                except:
                    break

        stop_ev = threading.Event()
        threading.Thread(target=_beep_loop, args=(stop_ev,), daemon=True).start()

        try:
            # 최대 30분 대기
            for _ in range(1800):
                self._wait(1)
                try:
                    url = self.driver.current_url
                    src = self.driver.page_source
                    done_kw = ["BookEnd", "결제완료", "예매완료", "주문완료",
                               "step3", "payment/complete"]
                    if any(k in url for k in done_kw):
                        self.log("✅ 결제 완료!")
                        stop_ev.set(); return
                except:
                    pass
            self.log("결제 대기 시간 초과 (30분)")
        finally:
            stop_ev.set()

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

            # 로그인 후 myaccount 등으로 가있으면 NOL 메인으로 이동
            try:
                if "nol.yanolja.com" not in self._url():
                    self.driver.get("https://nol.yanolja.com/")
                    self._wait(2)
            except: pass

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
            grade_idx, grade_list = self._ask_grade()
            self._wait(0.3)

            # ⑤ 구역 선택
            zones = self._ask_zones(grade_idx, grade_list)
            self.log(f"선택 구역: {', '.join(zones) if zones else '전체'}")
            self._wait(0.3)

            # ⑥ 구역 순회 + 좌석 클릭
            self._rotate_zones(zones, grade_idx, grade_list)

            # ⑦ 좌석선택완료
            self._click_complete()

            # ⑦-② 결제 페이지 진입 대기 (가격/할인선택 단계)
            self.log("결제 페이지 진입 대기 중...")
            for _ in range(60):
                self._wait(1)
                if self._is_payment_page():
                    break

            # ⑧ 결제 대기 + 소리 알림
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
