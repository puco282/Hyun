import streamlit as st
import pandas as pd
import gspread 
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# --- 페이지 기본 설정 ---
st.set_page_config(page_title="감정 일기장 (학생용)", page_icon="📘", layout="centered")

# --- 학생 시트 예상 헤더 ---
EXPECTED_STUDENT_SHEET_HEADER = ["날짜", "감정", "감사한 일", "하고 싶은 말", "선생님 쪽지"]
SETTINGS_ROW_DEFAULT = ["설정", "2000-01-01"] 

# --- Helper Functions ---
@st.cache_resource 
def authorize_gspread_student_final_v10(): # 버전업
    try:
        credentials_dict_student_final_v10 = st.secrets["GOOGLE_CREDENTIALS"]
        scope_student_final_v10 = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_student_final_v10 = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict_student_final_v10, scope_student_final_v10)
        return gspread.authorize(creds_student_final_v10)
    except Exception as e:
        st.error(f"Google API 인증 중 오류(학생앱): {e}. secrets 설정을 확인하세요."); st.stop(); return None

@st.cache_data(ttl=600) 
def get_students_df_for_student_app_v10(_client_gspread_student):
    if not _client_gspread_student: return pd.DataFrame()
    try:
        student_list_ws_s_app_v10 = _client_gspread_student.open("학생목록").sheet1
        df_s_app_v10 = pd.DataFrame(student_list_ws_s_app_v10.get_all_records(head=1)) 
        if not df_s_app_v10.empty:
            required_cols_s_app_v10 = ["이름", "비밀번호", "시트URL"]
            for col_s_app_v10 in required_cols_s_app_v10:
                if col_s_app_v10 not in df_s_app_v10.columns:
                    st.error(f"'학생목록' 시트에 필수 열인 '{col_s_app_v10}'이(가) 없습니다. 확인해주세요.")
                    return pd.DataFrame()
        return df_s_app_v10
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("'학생목록' 스프레드시트를 찾을 수 없습니다. 이름을 확인하고 공유 설정을 점검하세요."); return pd.DataFrame()
    except Exception as e:
        st.error(f"학생 목록 로딩 중 오류(학생앱): {e}. '학생목록' 시트 내용을 확인하세요."); return pd.DataFrame()

def get_records_from_row2_header_s_app_v10(worksheet_s, expected_header_list_s):
    all_values_s_app_v10 = worksheet_s.get_all_values()
    if len(all_values_s_app_v10) < 2: return [] 
    data_rows_s_app_v10 = all_values_s_app_v10[2:]
    records_s_app_v10 = []
    for r_vals_s_app_v10 in data_rows_s_app_v10:
        rec_s_app_v10 = {}
        for i_s_app_v10, header_name_s_app_v10 in enumerate(expected_header_list_s):
            rec_s_app_v10[header_name_s_app_v10] = r_vals_s_app_v10[i_s_app_v10] if i_s_app_v10 < len(r_vals_s_app_v10) else None
        records_s_app_v10.append(rec_s_app_v10)
    return records_s_app_v10

def ensure_sheet_structure_s_app_v10(worksheet_to_ensure, settings_content_s, header_content_s):
    try:
        all_vals_ensure_s_v10 = worksheet_to_ensure.get_all_values()
        if not all_vals_ensure_s_v10: 
            worksheet_to_ensure.append_row(settings_content_s, value_input_option='USER_ENTERED')
            worksheet_to_ensure.append_row(header_content_s, value_input_option='USER_ENTERED'); return
        current_r1_s_v10 = all_vals_ensure_s_v10[0]
        if len(current_r1_s_v10) < 1 or current_r1_s_v10[0] != settings_content_s[0]: worksheet_to_ensure.update_cell(1, 1, settings_content_s[0])
        if len(current_r1_s_v10) < 2 or not current_r1_s_v10[1]: worksheet_to_ensure.update_cell(1, 2, settings_content_s[1])
        if len(all_vals_ensure_s_v10) < 2: worksheet_to_ensure.append_row(header_content_s, value_input_option='USER_ENTERED')
        else:
            current_r2_s_v10 = all_vals_ensure_s_v10[1]
            if list(current_r2_s_v10) != header_content_s:
                try: 
                    header_end_col_letter_v10 = chr(ord('A') + len(header_content_s) - 1)
                    range_header_s_v10 = f'A2:{header_end_col_letter_v10}2'
                    worksheet_to_ensure.update(range_header_s_v10, [header_content_s], value_input_option='USER_ENTERED')
                except Exception: pass 
    except Exception: pass

# --- 세션 상태 초기화 ---
default_session_states_s_app_v10 = { 
    "student_logged_in": False, "student_page": "login", "student_name": None, 
    "student_sheet_url": None, "student_emotion": None, "student_gratitude": "", 
    "student_message": "", "student_selected_diary_date": None,
    "student_navigation_history": [], 
    "student_all_entries_cache": None, 
    "student_new_notes_to_display": [], 
    "notes_check_outcome": None # "check_notes" 페이지 결과 상태: None, "NOTES_FOUND", "NO_NEW_NOTES", "ERROR"
}
for key_s_v10, val_s_v10 in default_session_states_s_app_v10.items():
    if key_s_v10 not in st.session_state: st.session_state[key_s_v10] = val_s_v10

# --- 네비게이션 함수 (스택 활용) ---
def student_go_to_page_nav_v10(target_page_nav_s, **kwargs_nav):
    current_page_nav_s_v10 = st.session_state.student_page
    if current_page_nav_s_v10 != target_page_nav_s:
        if current_page_nav_s_v10 != "login": 
            if not st.session_state.student_navigation_history or st.session_state.student_navigation_history[-1] != current_page_nav_s_v10:
                st.session_state.student_navigation_history.append(current_page_nav_s_v10)
    
    for key_nav, value_nav in kwargs_nav.items(): 
        st.session_state[key_nav] = value_nav

    st.session_state.student_page = target_page_nav_s
    st.rerun()

def student_go_back_page_nav_v10():
    if st.session_state.student_page == "check_notes": # check_notes 페이지를 떠날 때 관련 상태 초기화
        st.session_state.notes_check_outcome = None
        st.session_state.student_new_notes_to_display = []

    if st.session_state.student_navigation_history:
        st.session_state.student_page = st.session_state.student_navigation_history.pop()
    else:
        st.session_state.student_page = "menu" 
    st.rerun()

def student_logout_nav_v10():
    for key_to_reset_nav_s_v10 in default_session_states_s_app_v10.keys():
        st.session_state[key_to_reset_nav_s_v10] = default_session_states_s_app_v10[key_to_reset_nav_s_v10]
    st.rerun()

# --- 학생 데이터 로드 및 캐시 함수 ---
def load_student_all_entries_cached_v10(g_client_s_app_v10, sheet_url_s_app_v10):
    if isinstance(st.session_state.student_all_entries_cache, pd.DataFrame):
        return st.session_state.student_all_entries_cache
    try:
        with st.spinner("학생 일기 데이터 로딩 중... (API 호출)"):
            ws_s_load_app_v10 = g_client_s_app_v10.open_by_url(sheet_url_s_app_v10).sheet1
            ensure_sheet_structure_s_app_v10(ws_s_load_app_v10, SETTINGS_ROW_DEFAULT, EXPECTED_STUDENT_SHEET_HEADER)
            records_s_load_app_v10 = get_records_from_row2_header_s_app_v10(ws_s_load_app_v10, EXPECTED_STUDENT_SHEET_HEADER)
            df_s_load_app_v10 = pd.DataFrame(records_s_load_app_v10)
            st.session_state.student_all_entries_cache = df_s_load_app_v10
            return df_s_load_app_v10
    except Exception as e_load_s_app_v10:
        st.error(f"학생 일기 데이터 로드 오류: {e_load_s_app_v10}"); return pd.DataFrame()

# --- MAIN STUDENT APP ---
g_client_student_main_v10 = authorize_gspread_student_final_v10()
students_df_login_v10 = get_students_df_for_student_app_v10(g_client_student_main_v10)

if st.session_state.student_page == "login":
    st.title("👧 감정 일기 로그인")
    s_name_in_v10 = st.text_input("이름", key="s_login_name_vfinal_10")
    s_pw_in_v10 = st.text_input("비밀번호 (6자리)", type="password", max_chars=6, key="s_login_pw_vfinal_10")

    if st.button("로그인", key="s_login_btn_vfinal_10"):
        s_name_login_v10, s_pw_login_v10 = s_name_in_v10.strip(), s_pw_in_v10.strip()
        if not s_name_login_v10 or not s_pw_login_v10: st.warning("이름과 비밀번호를 모두 입력하세요.")
        else:
            if students_df_login_v10.empty and g_client_student_main_v10:
                 st.error("'학생목록' 시트가 비었거나 접근할 수 없습니다. 관리자에게 문의하세요.")
            elif students_df_login_v10.empty and not g_client_student_main_v10: 
                 st.error("Google API 인증에 실패했습니다. secrets 설정을 확인하거나 관리자에게 문의하세요.")
            else:
                s_record_v10 = students_df_login_v10[students_df_login_v10["이름"] == s_name_login_v10]
                if not s_record_v10.empty and str(s_record_v10.iloc[0]["비밀번호"]).strip() == s_pw_login_v10:
                    for key_s_reset_v10, val_s_reset_v10 in default_session_states_s_app_v10.items():
                        st.session_state[key_s_reset_v10] = val_s_reset_v10
                    st.session_state.student_logged_in = True
                    st.session_state.student_name = s_name_login_v10
                    st.session_state.student_sheet_url = s_record_v10.iloc[0]["시트URL"]
                    # 로그인 후 'check_notes'로 이동하면서 관련 상태 초기화
                    student_go_to_page_nav_v10("check_notes", 
                                              notes_check_outcome=None, 
                                              student_new_notes_to_display=[])
                else: st.error("이름 또는 비밀번호가 틀립니다.")

elif st.session_state.student_logged_in:
    df_student_entries_main_v10 = load_student_all_entries_cached_v10(g_client_student_main_v10, st.session_state.student_sheet_url)

    if st.session_state.student_page == "check_notes":
        st.title(f"📬 {st.session_state.student_name}님, 선생님 쪽지 확인")
        
        # 버튼 클릭 전 초기 안내 메시지
        if st.session_state.notes_check_outcome is None:
            st.info("아래 '새로운 선생님 쪽지 확인하기 🔍' 버튼을 눌러 새 쪽지가 있는지 확인해보세요.")

        if st.button("새로운 선생님 쪽지 확인하기 🔍", key="s_check_new_notes_btn_vfinal_10"):
            new_notes_this_check_v10 = [] 
            with st.spinner("새로운 쪽지를 확인하는 중입니다... (API 호출 중)"):
                try:
                    student_sheet_url_notes_v10 = st.session_state.student_sheet_url
                    if not student_sheet_url_notes_v10:
                        st.error("학생 시트 정보를 찾을 수 없습니다."); st.stop()

                    ws_notes_v10 = g_client_student_main_v10.open_by_url(student_sheet_url_notes_v10).sheet1
                    ensure_sheet_structure_s_app_v10(ws_notes_v10, SETTINGS_ROW_DEFAULT, EXPECTED_STUDENT_SHEET_HEADER)
                    
                    last_checked_date_str_v10 = "2000-01-01"
                    try:
                        b1_val_v10 = ws_notes_v10.cell(1, 2).value
                        if b1_val_v10: last_checked_date_str_v10 = b1_val_v10
                    except Exception: pass 
                    
                    if not df_student_entries_main_v10.empty:
                        try: last_checked_dt_v10 = datetime.strptime(last_checked_date_str_v10, "%Y-%m-%d").date()
                        except ValueError: last_checked_dt_v10 = datetime.strptime("2000-01-01", "%Y-%m-%d").date()

                        for _, row_n_v10 in df_student_entries_main_v10.iterrows():
                            date_n_v10, note_n_v10 = row_n_v10.get("날짜"), str(row_n_v10.get("선생님 쪽지", "")).strip()
                            if note_n_v10 and date_n_v10:
                                try:
                                    if datetime.strptime(date_n_v10, "%Y-%m-%d").date() > last_checked_dt_v10:
                                        new_notes_this_check_v10.append((date_n_v10, note_n_v10))
                                except ValueError: continue                         
                        
                        update_b1_date_v10 = datetime.today().strftime("%Y-%m-%d")
                        if new_notes_this_check_v10: update_b1_date_v10 = new_notes_this_check_v10[-1][0]
                        
                        try: ws_notes_v10.update_cell(1, 2, update_b1_date_v10)
                        except Exception as e_b1: st.warning(f"확인 날짜 업데이트 실패: {e_b1}")
                    else: st.warning("일기 데이터가 없습니다.")

                    if new_notes_this_check_v10:
                        st.session_state.student_new_notes_to_display = sorted(new_notes_this_check_v10, key=lambda x: x[0])
                        st.session_state.notes_check_outcome = "NOTES_FOUND"
                    else:
                        st.session_state.student_new_notes_to_display = []
                        st.session_state.notes_check_outcome = "NO_NEW_NOTES"
                except Exception as e_notes: 
                    st.error(f"쪽지 확인 오류: {e_notes}")
                    st.session_state.notes_check_outcome = "ERROR"
            # 버튼 클릭 후에는 항상 rerun을 하여 변경된 session_state.notes_check_outcome을 바탕으로 아래 표시 로직이 실행되도록 함
            st.rerun() 

        # --- 쪽지 확인 결과 표시 ---
        # 이 부분은 st.button()의 if 블록 바깥에 있어야 rerun 후에 올바르게 표시됨
        if st.session_state.notes_check_outcome == "NOTES_FOUND":
            st.success(f"새로운 쪽지가 {len(st.session_state.student_new_notes_to_display)}개 도착했어요!")
            for date_d_v10, note_d_v10 in st.session_state.student_new_notes_to_display:
                st.markdown(f"**{date_d_v10}**: {note_d_v10}")
        elif st.session_state.notes_check_outcome == "NO_NEW_NOTES":
            st.info("새로운 선생님 쪽지가 없습니다.")
        elif st.session_state.notes_check_outcome == "ERROR":
            st.warning("쪽지를 확인하는 중 오류가 발생했습니다. 다시 시도해주세요.")
        # notes_check_outcome이 None일 경우 (초기 상태)는 페이지 상단의 st.info 안내 메시지가 표시됨
        
        st.divider()
        s_notes_cols1_v10, s_notes_cols2_v10 = st.columns(2)
        with s_notes_cols1_v10:
            if st.button("메인 메뉴", key="s_notes_to_menu_vfinal_10", use_container_width=True):
                student_go_to_page_nav_v10("menu", notes_check_outcome=None, student_new_notes_to_display=[])
        with s_notes_cols2_v10:
            if st.button("로그아웃", key="s_logout_notes_vfinal_10", use_container_width=True): student_logout_nav_v10()

    elif st.session_state.student_page == "menu":
        st.title(f"📘 {st.session_state.student_name}님 감정일기"); st.divider()
        if st.button("✏️ 오늘 일기 쓰기/수정", type="primary", use_container_width=True, key="s_menu_write_v10"):
            today_s_menu_v10 = datetime.today().strftime("%Y-%m-%d")
            st.session_state.student_emotion, st.session_state.student_gratitude, st.session_state.student_message = None, "", ""
            if not df_student_entries_main_v10.empty:
                today_entry_menu_v10 = df_student_entries_main_v10[df_student_entries_main_v10["날짜"] == today_s_menu_v10]
                if not today_entry_menu_v10.empty:
                    r_menu_v10 = today_entry_menu_v10.iloc[0]
                    st.session_state.student_emotion = r_menu_v10.get("감정")
                    st.session_state.student_gratitude = r_menu_v10.get("감사한 일", "")
                    st.session_state.student_message = r_menu_v10.get("하고 싶은 말", "")
            student_go_to_page_nav_v10("write_emotion")
        
        # ★★★ 메뉴명 변경 완료 ★★★
        if st.button("지난 일기 보기", use_container_width=True, key="s_menu_view_v10_renamed"):
            student_go_to_page_nav_v10("view_diary_only", student_selected_diary_date=None) 

        if st.button("새로운 선생님 쪽지 확인", use_container_width=True, key="s_menu_notes_v10"):
            student_go_to_page_nav_v10("check_notes", notes_check_outcome=None, student_new_notes_to_display=[])
        if st.button("로그아웃", use_container_width=True, key="s_logout_menu_v10"): student_logout_nav_v10()
    
    elif st.session_state.student_page == "write_emotion":
        st.title("😊 오늘의 감정"); st.caption("오늘 어떤 감정을 느꼈나요?")
        emo_dict_s_v10 = { "😀 긍정": ["기쁨", "감사", "자신감", "설렘", "평온"], "😐 보통": ["그냥 그래요", "지루함", "무난함"], "😢 부정": ["슬픔", "불안", "짜증", "화남", "피곤"] }
        cur_g_v10, cur_d_v10 = None, None
        if st.session_state.student_emotion:
            try: 
                g_v10, d_v10 = st.session_state.student_emotion.split(" - ",1)
                if g_v10 in emo_dict_s_v10 and d_v10 in emo_dict_s_v10[g_v10]: cur_g_v10, cur_d_v10 = g_v10, d_v10
            except ValueError: pass
        sel_g_v10 = st.selectbox("감정 그룹", list(emo_dict_s_v10.keys()), index=list(emo_dict_s_v10.keys()).index(cur_g_v10) if cur_g_v10 else 0, key="s_emo_g_vfinal_10")
        sel_d_v10 = st.selectbox("구체적 감정", emo_dict_s_v10[sel_g_v10], index=emo_dict_s_v10[sel_g_v10].index(cur_d_v10) if cur_d_v10 and cur_g_v10 == sel_g_v10 else 0, key="s_emo_d_vfinal_10")
        st.session_state.student_emotion = f"{sel_g_v10} - {sel_d_v10}"
        b1_we_v10,b2_we_v10 = st.columns(2)
        with b1_we_v10:
             if st.button("← 이전", key="s_emo_b_vfinal_10", use_container_width=True): student_go_back_page_nav_v10()
        with b2_we_v10:
            if st.button("다음 →", key="s_emo_n_vfinal_10", use_container_width=True, type="primary"): student_go_to_page_nav_v10("write_gratitude")

    elif st.session_state.student_page == "write_gratitude":
        st.title("🙏 감사한 일"); st.caption("오늘 어떤 점이 감사했나요?")
        st.session_state.student_gratitude = st.text_area("감사한 일", height=150, value=st.session_state.student_gratitude, key="s_grat_txt_vfinal_10", placeholder="사소한 것이라도 좋아요!")
        b1_wg_v10,b2_wg_v10 = st.columns(2)
        with b1_wg_v10:
            if st.button("← 이전", key="s_grat_b_vfinal_10", use_container_width=True): student_go_back_page_nav_v10()
        with b2_wg_v10:
            if st.button("다음 →", key="s_grat_n_vfinal_10", use_container_width=True, type="primary"): student_go_to_page_nav_v10("write_message")

    elif st.session_state.student_page == "write_message":
        st.title("💬 하고 싶은 말"); st.caption("선생님이나 친구, 또는 자신에게 하고 싶은 말을 자유롭게 적어보세요.")
        st.session_state.student_message = st.text_area("하고 싶은 말", height=200, value=st.session_state.student_message, key="s_msg_txt_vfinal_10", placeholder="어떤 이야기든 괜찮아요.")
        b1_wm_v10,b2_wm_v10 = st.columns(2)
        with b1_wm_v10:
            if st.button("← 이전", key="s_msg_b_vfinal_10", use_container_width=True): student_go_back_page_nav_v10()
        with b2_wm_v10:
            if st.button("다음 →", key="s_msg_n_vfinal_10", use_container_width=True, type="primary"): student_go_to_page_nav_v10("confirm_submission")

    elif st.session_state.student_page == "confirm_submission":
        st.title("✅ 내용 확인"); st.divider()
        st.write(f"**감정:** {st.session_state.student_emotion or '(선택 안 함)'}")
        st.write(f"**감사한 일:** {st.session_state.student_gratitude or '(내용 없음)'}")
        st.write(f"**하고 싶은 말:** {st.session_state.student_message or '(내용 없음)'}")
        st.divider()
        b1_cs_v10,b2_cs_v10 = st.columns(2)
        with b1_cs_v10:
            if st.button("← 수정하기", key="s_conf_b_vfinal_10", use_container_width=True): student_go_back_page_nav_v10()
        with b2_cs_v10:
            if st.button("✔️ 제출하기", key="s_submit_diary_vfinal_10", use_container_width=True, type="primary"):
                today_submit_s_v10 = datetime.today().strftime("%Y-%m-%d")
                try:
                    with st.spinner("일기 저장 중..."):
                        ws_s_submit_v10 = g_client_student_main_v10.open_by_url(st.session_state.student_sheet_url).sheet1
                        all_records_at_submit_v10 = get_records_from_row2_header_s_app_v10(ws_s_submit_v10, EXPECTED_STUDENT_SHEET_HEADER)
                        
                        existing_idx_s_v10, note_today_s_v10 = -1, ""
                        for idx_s_v10, r_s_submit_v10 in enumerate(all_records_at_submit_v10):
                            if r_s_submit_v10.get("날짜") == today_submit_s_v10:
                                existing_idx_s_v10, note_today_s_v10 = idx_s_v10, str(r_s_submit_v10.get("선생님 쪽지", "")); break
                        
                        new_data_s_v10 = [today_submit_s_v10, st.session_state.student_emotion,
                                          st.session_state.student_gratitude, st.session_state.student_message, note_today_s_v10]
                        
                        if existing_idx_s_v10 != -1: 
                            row_to_update_v10 = existing_idx_s_v10 + 3
                            end_col_letter_upd_v10 = chr(ord('A') + len(EXPECTED_STUDENT_SHEET_HEADER) - 1)
                            range_to_update_s_v10 = f'A{row_to_update_v10}:{end_col_letter_upd_v10}{row_to_update_v10}'
                            ws_s_submit_v10.update(range_to_update_s_v10, [new_data_s_v10], value_input_option='USER_ENTERED')
                            st.success("🔄 일기 수정 완료!")
                        else: 
                            ws_s_submit_v10.append_row(new_data_s_v10, value_input_option='USER_ENTERED')
                            st.success("🌟 일기 저장 완료!")
                        
                        st.session_state.student_all_entries_cache = None 
                        for k_form_s_v10 in ["student_emotion", "student_gratitude", "student_message"]: st.session_state[k_form_s_v10] = default_session_states_s_app_v10[k_form_s_v10]
                        st.session_state.student_selected_diary_date = today_submit_s_v10
                        st.session_state.student_navigation_history = [] 
                        st.balloons()
                        student_go_to_page_nav_v10("view_diary_only", notes_check_outcome=None, student_new_notes_to_display=[])
                except Exception as e_s_v10: st.error(f"일기 저장 오류: {e_s_v10}")

    # --- ★★★ 수정된 "지난 일기 보기" 페이지 (삭제 기능 없음) ★★★ ---
    elif st.session_state.student_page == "view_diary_only": 
        st.title("📖 지난 일기 보기"); st.divider() 
        if df_student_entries_main_v10.empty: st.info("작성된 일기가 없습니다.")
        else:
            dates_s_view_v10 = sorted(list(set(df_student_entries_main_v10["날짜"].dropna())), reverse=True)
            if not dates_s_view_v10: st.info("작성된 일기가 없습니다.")
            else:
                def_date_s_view_v10 = st.session_state.get("student_selected_diary_date")
                if not def_date_s_view_v10 or def_date_s_view_v10 not in dates_s_view_v10: 
                    def_date_s_view_v10 = dates_s_view_v10[0] if dates_s_view_v10 else datetime.today().strftime("%Y-%m-%d")
                
                sel_date_idx_v10 = dates_s_view_v10.index(def_date_s_view_v10) if def_date_s_view_v10 in dates_s_view_v10 else 0
                
                sel_date_s_v10 = st.selectbox(
                    "확인할 날짜 선택:", 
                    options=dates_s_view_v10, 
                    index=sel_date_idx_v10, 
                    key="s_diary_sel_vfinal_10_view_only"
                )
                st.session_state.student_selected_diary_date = sel_date_s_v10

                diary_s_v10 = df_student_entries_main_v10[df_student_entries_main_v10["날짜"] == sel_date_s_v10]
                if not diary_s_v10.empty:
                    r_s_view_v10 = diary_s_v10.iloc[0]
                    st.subheader(f"🗓️ {sel_date_s_v10} 일기")
                    st.write(f"**감정:** {r_s_view_v10.get('감정', '')}")
                    st.write(f"**감사한 일:** {r_s_view_v10.get('감사한 일', '')}")
                    st.write(f"**하고 싶은 말:** {r_s_view_v10.get('하고 싶은 말', '')}")
                    st.write(f"**선생님 쪽지:** {str(r_s_view_v10.get('선생님 쪽지', ''))}")
                    
                    # --- 삭제 버튼 및 관련 로직 완전 제거 ---
                    
                else: 
                    if sel_date_s_v10: 
                        st.info(f"{sel_date_s_v10}에 작성된 일기가 없습니다.")
        
        st.divider()
        s_view_cols1_v10_final, s_view_cols2_v10_final = st.columns(2)
        with s_view_cols1_v10_final:
            if st.button("뒤로가기", use_container_width=True, key="s_view_go_back_vfinal_10"): 
                student_go_back_page_nav_v10() 
        with s_view_cols2_v10_final:
            if st.button("로그아웃", use_container_width=True, key="s_logout_view_vfinal_10"): 
                student_logout_nav_v10()
else: 
    if st.session_state.student_page != "login": student_logout_nav_v10()
