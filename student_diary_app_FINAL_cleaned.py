# 감정 일기장 (학생용) - 전체 코드 정리본 with 최신 쪽지 확인 버튼 방식

import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- 페이지 기본 설정 ---
st.set_page_config(page_title="감정 일기장 (학생용)", page_icon="📘", layout="centered")

# --- 예상 시트 헤더 ---
EXPECTED_STUDENT_SHEET_HEADER = ["날짜", "감정", "감사한 일", "하고 싶은 말", "선생님 쪽지"]
SETTINGS_ROW_DEFAULT = ["설정", "2000-01-01"]

# --- 인증 및 데이터 로딩 ---
@st.cache_resource
def authorize_gspread():
    credentials = st.secrets["GOOGLE_CREDENTIALS"]
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials, scope)
    return gspread.authorize(creds)

@st.cache_data(ttl=600)
def get_students_df(client):
    try:
        ws = client.open("학생목록").sheet1
        df = pd.DataFrame(ws.get_all_records(head=1))
        for col in ["이름", "비밀번호", "시트URL"]:
            if col not in df.columns:
                st.error(f"'학생목록' 시트에 '{col}' 열이 없습니다."); return pd.DataFrame()
        return df
    except:
        st.error("학생 목록 로딩 실패"); return pd.DataFrame()

# --- 시트 구조 보장 ---
def ensure_sheet_structure(ws, settings_row, header_row):
    all_vals = ws.get_all_values()
    if not all_vals:
        ws.append_row(settings_row, value_input_option='USER_ENTERED')
        ws.append_row(header_row, value_input_option='USER_ENTERED')
        return
    if len(all_vals) < 2:
        ws.append_row(header_row, value_input_option='USER_ENTERED')

# --- 세션 상태 초기화 ---
def init_session():
    defaults = {
        "student_logged_in": False, "student_page": "login", "student_name": None,
        "student_sheet_url": None, "student_checked_notes_button_clicked": False,
        "student_new_notes_to_display": [], "student_entries": None,
        "student_emotion": None, "student_gratitude": "", "student_message": ""
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()

# --- 네비게이션 ---
def go_to(page, **kwargs):
    st.session_state.student_page = page
    for k, v in kwargs.items():
        st.session_state[k] = v
    st.rerun()

def logout():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    init_session()
    st.rerun()

# --- 인증 및 데이터 ---
g_client = authorize_gspread()
students_df = get_students_df(g_client)

# --- 로그인 페이지 ---
if st.session_state.student_page == "login":
    st.title("👧 감정 일기 로그인")
    name = st.text_input("이름")
    pw = st.text_input("비밀번호 (6자리)", type="password", max_chars=6)

    if st.button("로그인"):
        record = students_df[students_df["이름"] == name.strip()]
        if not record.empty and str(record.iloc[0]["비밀번호"]).strip() == pw.strip():
            st.session_state.student_logged_in = True
            st.session_state.student_name = name.strip()
            st.session_state.student_sheet_url = record.iloc[0]["시트URL"]
            go_to("check_notes", student_checked_notes_button_clicked=False, student_new_notes_to_display=[])
        else:
            st.error("이름 또는 비밀번호가 틀립니다.")

# --- 로그인 후 페이지들 ---
elif st.session_state.student_logged_in:

    def load_entries():
        try:
            if st.session_state.student_entries is not None:
                return st.session_state.student_entries
            ws = g_client.open_by_url(st.session_state.student_sheet_url).sheet1
            ensure_sheet_structure(ws, SETTINGS_ROW_DEFAULT, EXPECTED_STUDENT_SHEET_HEADER)
            data = ws.get_all_values()[2:]
            entries = [dict(zip(EXPECTED_STUDENT_SHEET_HEADER, row + [""] * (5 - len(row)))) for row in data]
            df = pd.DataFrame(entries)
            st.session_state.student_entries = df
            return df
        except:
            return pd.DataFrame()

    if st.session_state.student_page == "check_notes":
        st.title(f"📬 {st.session_state.student_name}님, 선생님 쪽지 확인")

        if not st.session_state.student_checked_notes_button_clicked:
            if st.button("📬 선생님 쪽지 확인", use_container_width=True):
                st.session_state.student_checked_notes_button_clicked = True
                st.session_state.student_new_notes_to_display = []
                try:
                    ws = g_client.open_by_url(st.session_state.student_sheet_url).sheet1
                    ensure_sheet_structure(ws, SETTINGS_ROW_DEFAULT, EXPECTED_STUDENT_SHEET_HEADER)
                    all_vals = ws.get_all_values()

                    # B1에 있는 마지막 확인 날짜 확인
                    last_checked_date = "2000-01-01"
                    try:
                        b1_val = ws.cell(1, 2).value
                        if b1_val:
                            last_checked_date = b1_val.strip()
                    except:
                        pass

                    new_notes = []
                    for row in reversed(all_vals[2:]):
                        if len(row) >= 5 and row[4].strip():
                            try:
                                note_date = datetime.strptime(row[0], "%Y-%m-%d").date()
                                if note_date > datetime.strptime(last_checked_date, "%Y-%m-%d").date():
                                    new_notes.append({"날짜": row[0], "쪽지": row[4].strip()})
                            except:
                                continue

                    if new_notes:
                        st.session_state.student_new_notes_to_display = sorted(new_notes, key=lambda x: x["날짜"])
                        latest_date = st.session_state.student_new_notes_to_display[-1]["날짜"]
                        try:
                            ws.update_cell(1, 2, latest_date)
                        except:
                            pass
                except Exception as e:
                    st.error(f"쪽지 확인 오류: {e}")
                    st.session_state.student_checked_notes_button_clicked = False

        if st.session_state.student_checked_notes_button_clicked:
            notes = st.session_state.student_new_notes_to_display
            if notes:
                st.success(f"새로운 쪽지가 {len(notes)}개 도착했어요!")
                for note in notes:
                    st.markdown(f"**{note['날짜']}**: {note['쪽지']}")
            else:
                st.info("새로운 선생님 쪽지가 없습니다.")

        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            if st.button("메인 메뉴", use_container_width=True):
                go_to("menu", student_checked_notes_button_clicked=False, student_new_notes_to_display=[])
        with col2:
            if st.button("로그아웃", use_container_width=True):
                logout()

    # --- 메뉴 페이지 ---
    elif st.session_state.student_page == "menu":
        st.title(f"📘 {st.session_state.student_name}님 감정일기")
        st.divider()
        if st.button("✏️ 오늘 일기 쓰기/수정", use_container_width=True):
            go_to("write_emotion")
        if st.button("📖 지난 일기 보기/삭제", use_container_width=True):
            go_to("view_modify")
        if st.button("📬 선생님 쪽지 다시 확인", use_container_width=True):
            go_to("check_notes", student_checked_notes_button_clicked=False, student_new_notes_to_display=[])
        if st.button("로그아웃", use_container_width=True):
            logout()

    # --- 감정 선택 페이지 ---
    elif st.session_state.student_page == "write_emotion":
        st.title("😊 오늘의 감정")
        emo_groups = {"😀 긍정": ["기쁨", "감사", "자신감", "설렘", "평온"], "😐 보통": ["그냥 그래요", "지루함"], "😢 부정": ["슬픔", "불안", "짜증"]}
        group = st.selectbox("감정 그룹", list(emo_groups.keys()))
        detail = st.selectbox("감정", emo_groups[group])
        st.session_state.student_emotion = f"{group} - {detail}"
        if st.button("다음 →", use_container_width=True):
            go_to("write_gratitude")

    # --- 감사한 일 작성 페이지 ---
    elif st.session_state.student_page == "write_gratitude":
        st.title("🙏 감사한 일")
        st.session_state.student_gratitude = st.text_area("감사한 일", value=st.session_state.student_gratitude)
        if st.button("다음 →", use_container_width=True):
            go_to("write_message")

    # --- 하고 싶은 말 작성 페이지 ---
    elif st.session_state.student_page == "write_message":
        st.title("💬 하고 싶은 말")
        st.session_state.student_message = st.text_area("하고 싶은 말", value=st.session_state.student_message)
        if st.button("제출하기 ✅", use_container_width=True):
            try:
                ws = g_client.open_by_url(st.session_state.student_sheet_url).sheet1
                today = datetime.today().strftime("%Y-%m-%d")
                new_data = [today, st.session_state.student_emotion, st.session_state.student_gratitude, st.session_state.student_message, ""]
                rows = ws.get_all_values()[2:]
                updated = False
                for i, row in enumerate(rows):
                    if row[0] == today:
                        ws.update(f"A{i+3}:E{i+3}", [new_data], value_input_option="USER_ENTERED")
                        updated = True; break
                if not updated:
                    ws.append_row(new_data, value_input_option="USER_ENTERED")
                st.success("일기 저장 완료!")
                st.session_state.student_entries = None
                go_to("menu")
            except Exception as e:
                st.error(f"저장 중 오류: {e}")

    # --- 지난 일기 보기/삭제 페이지 ---
    elif st.session_state.student_page == "view_modify":
        st.title("📖 지난 일기 보기/삭제")
        df = load_entries()
        if df.empty:
            st.info("작성된 일기가 없습니다.")
        else:
            date = st.selectbox("날짜 선택", options=sorted(df["날짜"], reverse=True))
            sel = df[df["날짜"] == date].iloc[0]
            st.markdown(f"**감정**: {sel['감정']}")
            st.markdown(f"**감사한 일**: {sel['감사한 일']}")
            st.markdown(f"**하고 싶은 말**: {sel['하고 싶은 말']}")
            st.markdown(f"**선생님 쪽지**: {sel['선생님 쪽지']}")
            if st.button("❌ 삭제", type="primary"):
                try:
                    ws = g_client.open_by_url(st.session_state.student_sheet_url).sheet1
                    rows = ws.get_all_values()[2:]
                    for i, row in enumerate(rows):
                        if row[0] == date:
                            ws.delete_rows(i + 3)
                            st.success(f"{date} 일기 삭제 완료")
                            st.session_state.student_entries = None
                            st.rerun()
                            break
                except Exception as e:
                    st.error(f"삭제 오류: {e}")
        if st.button("메인 메뉴", use_container_width=True):
            go_to("menu")
