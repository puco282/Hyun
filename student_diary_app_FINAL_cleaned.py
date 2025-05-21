import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
# from collections import deque # 큐는 이번 버전에서 직접적인 UI로 구현하지 않음

# --- 페이지 기본 설정 ---
st.set_page_config(page_title="감정 일기장 (학생용)", page_icon="📘", layout="centered")

# --- 학생 시트 예상 헤더 ---
EXPECTED_STUDENT_SHEET_HEADER = ["날짜", "감정", "감사한 일", "하고 싶은 말", "선생님 쪽지"]
SETTINGS_ROW_DEFAULT = ["설정", "2000-01-01"] # 학생 시트 B1셀 기본값 (마지막 쪽지 확인 날짜)

# --- Helper Functions ---
@st.cache_resource # 리소스 캐싱 (gspread 클라이언트 객체)
def authorize_gspread_student_final():
    try:
        credentials_dict_student_final = st.secrets["GOOGLE_CREDENTIALS"]
        scope_student_final = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_student_final = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict_student_final, scope_student_final)
        client_gspread_student_final = gspread.authorize(creds_student_final)
        return client_gspread_student_final
    except Exception as e:
        st.error(f"Google API 인증 중 오류(학생앱): {e}. secrets 설정을 확인하세요."); st.stop(); return None

@st.cache_data(ttl=600) # 학생 목록은 10분간 캐시
def get_students_df_for_student_app(_client_gspread_student):
    if not _client_gspread_student: return pd.DataFrame()
    try:
        student_list_ws_s_app = _client_gspread_student.open("학생목록").sheet1
        df_s_app = pd.DataFrame(student_list_ws_s_app.get_all_records(head=1)) # 첫 행을 헤더로
        if not df_s_app.empty:
            required_cols = ["이름", "비밀번호", "시트URL"]
            for col in required_cols:
                if col not in df_s_app.columns:
                    st.error(f"'학생목록' 시트에 필수 열인 '{col}'이(가) 없습니다. 확인해주세요.")
                    return pd.DataFrame()
        return df_s_app
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("'학생목록' 스프레드시트를 찾을 수 없습니다. 이름을 확인하고 공유 설정을 점검하세요."); return pd.DataFrame()
    except Exception as e:
        st.error(f"학생 목록 로딩 중 오류(학생앱): {e}. '학생목록' 시트 내용을 확인하세요."); return pd.DataFrame()

def get_records_from_row2_header_s_app(worksheet_s, expected_header_list_s):
    all_values_s_app = worksheet_s.get_all_values()
    if len(all_values_s_app) < 2: return [] # 설정행(1행), 헤더행(2행) 필수
    data_rows_s_app = all_values_s_app[2:]
    records_s_app = []
    num_expected_headers_s_app = len(expected_header_list_s)
    for r_vals_s_app in data_rows_s_app:
        rec_s_app = {}
        for i_s_app, header_name_s_app in enumerate(expected_header_list_s):
            rec_s_app[header_name_s_app] = r_vals_s_app[i_s_app] if i_s_app < len(r_vals_s_app) else None
        records_s_app.append(rec_s_app)
    return records_s_app

def ensure_sheet_structure_s_app(worksheet_to_ensure, settings_content_s, header_content_s):
    try:
        all_vals_ensure_s = worksheet_to_ensure.get_all_values()
        if not all_vals_ensure_s: # 시트가 완전히 비었을 때
            worksheet_to_ensure.append_row(settings_content_s, value_input_option='USER_ENTERED')
            worksheet_to_ensure.append_row(header_content_s, value_input_option='USER_ENTERED')
            return

        current_r1_s = all_vals_ensure_s[0]
        if len(current_r1_s) < 1 or current_r1_s[0] != settings_content_s[0]: worksheet_to_ensure.update_cell(1, 1, settings_content_s[0])
        if len(current_r1_s) < 2 or not current_r1_s[1]: worksheet_to_ensure.update_cell(1, 2, settings_content_s[1])
        
        if len(all_vals_ensure_s) < 2: # 헤더 행이 없는 경우
            worksheet_to_ensure.append_row(header_content_s, value_input_option='USER_ENTERED')
        else: # 헤더 행이 있지만 내용이 다를 경우
            current_r2_s = all_vals_ensure_s[1]
            if list(current_r2_s) != header_content_s:
                try: # 헤더 업데이트 시도
                    range_header_s = f'A2:{gspread.utils.rowcol_to_a1(2, len(header_content_s))}'
                    worksheet_to_ensure.update(range_header_s, [header_content_s], value_input_option='USER_ENTERED')
                except Exception: pass # 실패해도 일단 진행
    except Exception: pass # 전체 구조 확인 실패해도 일단 진행 (API 호출 최소화)

# --- 세션 상태 초기화 ---
default_session_states_s_app = {
    "student_logged_in": False, "student_page": "login", "student_name": None, 
    "student_sheet_url": None, "student_emotion": None, "student_gratitude": "", 
    "student_message": "", "student_selected_diary_date": None,
    "student_navigation_history": [], 
    "student_all_entries_cache": None, # 학생 자신의 전체 일기 캐시 (DataFrame)
    "student_new_notes_to_display": [], 
    "student_checked_notes_button_clicked": False # 쪽지 확인 버튼 클릭 여부
}
for key_student_app, val_student_app in default_session_states_s_app.items():
    if key_student_app not in st.session_state:
        st.session_state[key_student_app] = val_student_app

# --- 네비게이션 함수 (스택 활용) ---
def student_go_to_page_nav(target_page_nav_s):
    current_page_nav_s = st.session_state.student_page
    if current_page_nav_s != target_page_nav_s:
        if current_page_nav_s != "login": 
            if not st.session_state.student_navigation_history or st.session_state.student_navigation_history[-1] != current_page_nav_s:
                st.session_state.student_navigation_history.append(current_page_nav_s)
        st.session_state.student_page = target_page_nav_s
        st.rerun()

def student_go_back_page_nav():
    if st.session_state.student_navigation_history:
        st.session_state.student_page = st.session_state.student_navigation_history.pop()
    else:
        st.session_state.student_page = "menu" 
    st.rerun()

def student_logout_nav():
    for key_to_reset_nav_s in default_session_states_s_app.keys():
        st.session_state[key_to_reset_nav_s] = default_session_states_s_app[key_to_reset_nav_s]
    st.rerun()

# --- 학생 데이터 로드 및 캐시 함수 ---
def load_student_all_entries_cached(g_client_s_app, sheet_url_s_app):
    if st.session_state.student_all_entries_cache is not None:
        return st.session_state.student_all_entries_cache, True # 캐시 사용
    try:
        with st.spinner("일기 데이터 로딩 중... (API 호출)"):
            ws_s_load_app = g_client_s_app.open_by_url(sheet_url_s_app).sheet1
            ensure_sheet_structure_s_app(ws_s_load_app, SETTINGS_ROW_DEFAULT, EXPECTED_STUDENT_SHEET_HEADER)
            records_s_load_app = get_records_from_row2_header_s_app(ws_s_load_app, EXPECTED_STUDENT_SHEET_HEADER)
            df_s_load_app = pd.DataFrame(records_s_load_app)
            st.session_state.student_all_entries_cache = df_s_load_app
            return df_s_load_app, False # 새로 로드
    except Exception as e_load_s_app:
        st.error(f"일기 데이터 로드 오류: {e_load_s_app}"); return pd.DataFrame(), False

# --- MAIN STUDENT APP ---
g_client_student_main = authorize_gspread_student_final()
students_df_login = get_students_df_for_student_app(g_client_student_main)

if st.session_state.student_page == "login":
    st.title("👧 감정 일기 로그인")
    s_name_in = st.text_input("이름", key="s_login_name_vfinal")
    s_pw_in = st.text_input("비밀번호 (6자리)", type="password", max_chars=6, key="s_login_pw_vfinal")

    if st.button("로그인", key="s_login_btn_vfinal"):
        s_name_login, s_pw_login = s_name_in.strip(), s_pw_in.strip()
        if not s_name_login or not s_pw_login: st.warning("이름과 비밀번호를 모두 입력하세요.")
        else:
            if students_df_login.empty and g_client_student_main:
                 st.error("'학생목록' 시트가 비었거나 접근 불가. 관리자에게 문의.")
            else:
                s_record = students_df_login[students_df_login["이름"] == s_name_login]
                if not s_record.empty and str(s_record.iloc[0]["비밀번호"]).strip() == s_pw_login:
                    for key_s_reset, val_s_reset in default_session_states_s_app.items(): # 로그인 시 세션 초기화
                        st.session_state[key_s_reset] = val_s_reset
                    st.session_state.student_logged_in = True
                    st.session_state.student_name = s_name_login
                    st.session_state.student_sheet_url = s_record.iloc[0]["시트URL"]
                    student_go_to_page_nav("check_notes") 
                else: st.error("이름 또는 비밀번호가 틀립니다.")

elif st.session_state.student_logged_in:
    df_student_entries_main, from_cache = load_student_all_entries_cached(g_client_student_main, st.session_state.student_sheet_url)

    if st.session_state.student_page == "check_notes":
        st.title(f"📬 {st.session_state.student_name}님, 선생님 쪽지")
        st.markdown("아래 버튼을 눌러 새 쪽지가 있는지 확인하세요.")

        if st.button("새로운 선생님 쪽지 확인하기 🔍", key="s_check_notes_btn_vfinal"):
            st.session_state.student_new_notes_to_display = [] 
            st.session_state.student_checked_notes_button_clicked = True
            
            with st.spinner("새로운 쪽지를 확인하는 중입니다..."):
                try:
                    ws_notes = g_client_student_main.open_by_url(st.session_state.student_sheet_url).sheet1 # B1셀 읽기/쓰기용
                    ensure_sheet_structure_s_app(ws_notes, SETTINGS_ROW_DEFAULT, EXPECTED_STUDENT_SHEET_HEADER)
                    
                    last_checked_date_str_s = "2000-01-01"
                    try: b1_val_s = ws_notes.cell(1, 2).value;_ =0 
                    except Exception: pass
                    if b1_val_s: last_checked_date_str_s = b1_val_s
                                        
                    if not df_student_entries_main.empty:
                        new_notes_list_s = []
                        try: last_checked_dt_s = datetime.strptime(last_checked_date_str_s, "%Y-%m-%d").date()
                        except ValueError: last_checked_dt_s = datetime.strptime("2000-01-01", "%Y-%m-%d").date()

                        for _, row_n in df_student_entries_main.iterrows():
                            date_n, note_n = row_n.get("날짜"), str(row_n.get("선생님 쪽지", "")).strip()
                            if note_n and date_n:
                                try:
                                    if datetime.strptime(date_n, "%Y-%m-%d").date() > last_checked_dt_s:
                                        new_notes_list_s.append((date_n, note_n))
                                except ValueError: continue
                        st.session_state.student_new_notes_to_display = sorted(new_notes_list_s, key=lambda x: x[0])
                        
                        update_b1_date = datetime.today().strftime("%Y-%m-%d")
                        if new_notes_list_s: update_b1_date = new_notes_list_s[-1][0]
                        ws_notes.update_cell(1, 2, update_b1_date)
                    else: st.warning("일기 데이터가 없습니다.")
                except Exception as e: st.error(f"쪽지 확인 오류: {e}")

        if st.session_state.student_checked_notes_button_clicked:
            if st.session_state.student_new_notes_to_display:
                st.success(f"새로운 쪽지 {len(st.session_state.student_new_notes_to_display)}개 도착!")
                for date_d, note_d in st.session_state.student_new_notes_to_display: st.markdown(f"**{date_d}**: {note_d}")
            else: st.info("새로운 선생님 쪽지가 없습니다.")
        
        s_notes_col1, s_notes_col2 = st.columns(2)
        with s_notes_col1:
            if st.button("메인 메뉴", key="s_notes_to_menu_vfinal"): student_go_to_page_nav("menu")
        with s_notes_col2:
            if st.button("로그아웃", key="s_logout_notes_vfinal"): student_logout_nav()

    elif st.session_state.student_page == "menu":
        st.title(f"📘 {st.session_state.student_name}님 감정일기"); st.divider()
        if st.button("✏️ 오늘 일기 쓰기/수정", type="primary", use_container_width=True, key="s_menu_to_write_vfinal"):
            today_s = datetime.today().strftime("%Y-%m-%d")
            st.session_state.student_emotion, st.session_state.student_gratitude, st.session_state.student_message = None, "", ""
            if not df_student_entries_main.empty:
                today_e = df_student_entries_main[df_student_entries_main["날짜"] == today_s]
                if not today_e.empty:
                    r = today_e.iloc[0]
                    st.session_state.student_emotion, st.session_state.student_gratitude, st.session_state.student_message = r.get("감정"), r.get("감사한 일", ""), r.get("하고 싶은 말", "")
            student_go_to_page_nav("write_emotion")
        
        if st.button("지난 일기 보기/삭제", use_container_width=True, key="s_menu_to_view_vfinal"):
            st.session_state.student_selected_diary_date = None; student_go_to_page_nav("view_modify_diary")
        if st.button("새로운 선생님 쪽지 확인", use_container_width=True, key="s_menu_to_notes_vfinal"):
            st.session_state.student_checked_notes_button_clicked = False; st.session_state.student_new_notes_to_display = []
            student_go_to_page_nav("check_notes")
        if st.button("로그아웃", use_container_width=True, key="s_logout_menu_vfinal"): student_logout_nav()

    elif st.session_state.student_page == "write_emotion":
        st.title("😊 오늘의 감정"); st.caption("오늘 어떤 감정을 느꼈나요?")
        emo_dict = { "😀 긍정": ["기쁨", "감사", "자신감", "설렘", "평온"],
                     "😐 보통": ["그냥 그래요", "지루함", "무난함"],
                     "😢 부정": ["슬픔", "불안", "짜증", "화남", "피곤"] }
        cur_g, cur_d = None, None
        if st.session_state.student_emotion:
            try:
                g, d = st.session_state.student_emotion.split(" - ", 1)
                if g in emo_dict and d in emo_dict[g]: cur_g, cur_d = g, d
            except ValueError: pass
        sel_g = st.selectbox("감정 그룹", list(emo_dict.keys()), index=list(emo_dict.keys()).index(cur_g) if cur_g else 0, key="s_emo_g_vfinal")
        sel_d = st.selectbox("구체적 감정", emo_dict[sel_g], index=emo_dict[sel_g].index(cur_d) if cur_d and cur_g == sel_g else 0, key="s_emo_d_vfinal")
        st.session_state.student_emotion = f"{sel_g} - {sel_d}"
        b1,b2 = st.columns(2);b1.button("← 이전 (메뉴)", on_click=student_go_back_page_nav, key="s_emo_b_vfinal", use_container_width=True);b2.button("다음 →", on_click=student_go_to_page_nav, args=("write_gratitude",), key="s_emo_n_vfinal", use_container_width=True, type="primary")

    elif st.session_state.student_page == "write_gratitude":
        st.title("🙏 감사한 일"); st.caption("오늘 어떤 점이 감사했나요?")
        st.session_state.student_gratitude = st.text_area("감사한 일", height=150, value=st.session_state.student_gratitude, key="s_grat_txt_vfinal", placeholder="사소한 것이라도 좋아요!")
        b1,b2 = st.columns(2);b1.button("← 이전", on_click=student_go_back_page_nav, key="s_grat_b_vfinal", use_container_width=True);b2.button("다음 →", on_click=student_go_to_page_nav, args=("write_message",), key="s_grat_n_vfinal", use_container_width=True, type="primary")

    elif st.session_state.student_page == "write_message":
        st.title("💬 하고 싶은 말"); st.caption("선생님이나 친구, 또는 자신에게 하고 싶은 말을 자유롭게 적어보세요.")
        st.session_state.student_message = st.text_area("하고 싶은 말", height=200, value=st.session_state.student_message, key="s_msg_txt_vfinal", placeholder="어떤 이야기든 괜찮아요.")
        b1,b2 = st.columns(2);b1.button("← 이전", on_click=student_go_back_page_nav, key="s_msg_b_vfinal", use_container_width=True);b2.button("다음 →", on_click=student_go_to_page_nav, args=("confirm_submission",), key="s_msg_n_vfinal", use_container_width=True, type="primary")

    elif st.session_state.student_page == "confirm_submission":
        st.title("✅ 내용 확인"); st.divider()
        st.write(f"**감정:** {st.session_state.student_emotion or '(선택 안 함)'}")
        st.write(f"**감사한 일:** {st.session_state.student_gratitude or '(내용 없음)'}")
        st.write(f"**하고 싶은 말:** {st.session_state.student_message or '(내용 없음)'}")
        st.divider()
        b1,b2 = st.columns(2);b1.button("← 수정하기", on_click=student_go_back_page_nav, key="s_conf_b_vfinal", use_container_width=True)
        if b2.button("✔️ 제출하기", key="s_submit_diary_vfinal", use_container_width=True, type="primary"):
            today_submit_s = datetime.today().strftime("%Y-%m-%d")
            try:
                with st.spinner("일기 저장 중..."):
                    ws_submit_s = g_client_student_main.open_by_url(st.session_state.student_sheet_url).sheet1
                    # 저장 시에는 최신 상태 확인을 위해 df_student_entries_main (캐시된 데이터)를 다시 로드하거나,
                    # 원본 리스트로 인덱스 찾기. 여기서는 df_student_entries_main의 원본 리스트를 찾아야 함.
                    # 안전하게는 df_student_entries_main을 한 번 더 로드하는 방법도 있음.
                    # 여기서는 캐시된 df_student_entries_main을 활용
                    df_for_submit = df_student_entries_main.copy() # 방어적 복사
                    existing_entry_df = df_for_submit[df_for_submit["날짜"] == today_submit_s]
                    note_for_today_s_submit = ""
                    if not existing_entry_df.empty:
                        note_for_today_s_submit = str(existing_entry_df.iloc[0].get("선생님 쪽지", ""))
                    
                    new_data_to_submit = [today_submit_s, st.session_state.student_emotion,
                                          st.session_state.student_gratitude, st.session_state.student_message, note_for_today_s_submit]
                    
                    # 실제 행 인덱스를 찾기 위해 시트 다시 읽기 (정확성을 위해)
                    temp_records_for_idx = get_records_from_row2_header_s_app(ws_submit_s, EXPECTED_STUDENT_SHEET_HEADER)
                    actual_row_idx = -1
                    for idx, r_find in enumerate(temp_records_for_idx):
                        if r_find.get("날짜") == today_submit_s: actual_row_idx = idx + 3; break # 0-based + 3 (1-based + 2 offset)
                    
                    if actual_row_idx != -1: # 업데이트
                        range_to_update_s = f'A{actual_row_idx}:{gspread.utils.rowcol_to_a1(actual_row_idx, len(EXPECTED_STUDENT_SHEET_HEADER))}'
                        ws_submit_s.update(range_to_update_s, [new_data_to_submit], value_input_option='USER_ENTERED')
                        st.success("🔄 일기 수정 완료!")
                    else: # 새로 추가
                        ws_submit_s.append_row(new_data_to_submit, value_input_option='USER_ENTERED')
                        st.success("🌟 일기 저장 완료!")
                    
                    st.session_state.student_all_entries_cache = None # 캐시 무효화
                    for k_form in ["student_emotion", "student_gratitude", "student_message"]: st.session_state[k_form] = defaults_student_session[k_form] # 입력 폼 초기화
                    st.session_state.student_selected_diary_date = today_submit_s
                    st.session_state.student_navigation_history = [] # 제출 후 히스토리 클리어
                    st.balloons(); student_go_to_page_nav("view_modify_diary")
            except Exception as e_s: st.error(f"일기 저장 오류: {e_s}")

    elif st.session_state.student_page == "view_modify_diary":
        st.title("📖 지난 일기 보기/삭제"); st.divider()
        if df_student_entries_main.empty: st.info("작성된 일기가 없습니다.")
        else:
            dates_s_view = sorted(list(set(df_student_entries_main["날짜"].dropna())), reverse=True)
            if not dates_s_view: st.info("작성된 일기가 없습니다.")
            else:
                def_date_s_view = st.session_state.get("student_selected_diary_date")
                if not def_date_s_view or def_date_s_view not in dates_s_view: def_date_s_view = dates_s_view[0]
                
                sel_date_idx = dates_s_view.index(def_date_s_view) if def_date_s_view in dates_s_view else 0
                sel_date_s = st.selectbox("날짜 선택:", options=dates_s_view, index=sel_date_idx, key="s_diary_sel_vfinal")
                st.session_state.student_selected_diary_date = sel_date_s

                diary_s = df_student_entries_main[df_student_entries_main["날짜"] == sel_date_s]
                if not diary_s.empty:
                    r_s_view = diary_s.iloc[0]
                    st.subheader(f"🗓️ {sel_date_s} 일기")
                    st.write(f"**감정:** {r_s_view.get('감정', '')}")
                    st.write(f"**감사한 일:** {r_s_view.get('감사한 일', '')}")
                    st.write(f"**하고 싶은 말:** {r_s_view.get('하고 싶은 말', '')}")
                    st.write(f"**선생님 쪽지:** {str(r_s_view.get('선생님 쪽지', ''))}")

                    if st.button(f"❌ {sel_date_s} 일기 삭제", key="s_delete_btn_vfinal", type="warning"):
                        try:
                            with st.spinner("일기 삭제 중..."):
                                ws_s_del = g_client_student_main.open_by_url(st.session_state.student_sheet_url).sheet1
                                temp_recs_for_del = get_records_from_row2_header_s_app(ws_s_del, EXPECTED_STUDENT_SHEET_HEADER)
                                row_to_del_idx = -1
                                for idx_del, r_del in enumerate(temp_recs_for_del):
                                    if r_del.get("날짜") == sel_date_s: row_to_del_idx = idx_del + 3; break
                                
                                if row_to_del_idx != -1:
                                    ws_s_del.delete_rows(row_to_del_idx)
                                    st.session_state.student_all_entries_cache = None # 캐시 무효화
                                    st.success(f"✅ {sel_date_s} 일기 삭제 완료.")
                                    st.session_state.student_selected_diary_date = None; st.rerun()
                                else: st.error("삭제할 일기를 시트에서 찾지 못했습니다.")
                        except Exception as e_s_del: st.error(f"일기 삭제 오류: {e_s_del}")
                else: st.info(f"{sel_date_s}에 작성된 일기가 없습니다.")
        
        s_view_cols1, s_view_cols2 = st.columns(2)
        with s_view_cols1:
            if st.button("메인 메뉴", use_container_width=True, key="s_view_to_menu_vfinal"): student_go_to_page_nav("menu")
        with s_view_cols2:
            if st.button("로그아웃", use_container_width=True, key="s_logout_view_vfinal"): student_logout_nav()
else: 
    if st.session_state.student_page != "login": student_logout_nav()
