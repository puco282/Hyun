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
def authorize_gspread_student_final_v7(): # 버전업
    try:
        credentials_dict_student_final_v7 = st.secrets["GOOGLE_CREDENTIALS"]
        scope_student_final_v7 = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_student_final_v7 = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict_student_final_v7, scope_student_final_v7)
        client_gspread_student_final_v7 = gspread.authorize(creds_student_final_v7)
        return client_gspread_student_final_v7
    except Exception as e:
        st.error(f"Google API 인증 중 오류(학생앱): {e}. secrets 설정을 확인하세요."); st.stop(); return None

@st.cache_data(ttl=600) 
def get_students_df_for_student_app_v7(_client_gspread_student):
    if not _client_gspread_student: return pd.DataFrame()
    try:
        student_list_ws_s_app_v7 = _client_gspread_student.open("학생목록").sheet1
        df_s_app_v7 = pd.DataFrame(student_list_ws_s_app_v7.get_all_records(head=1)) 
        if not df_s_app_v7.empty:
            required_cols_s_app_v7 = ["이름", "비밀번호", "시트URL"]
            for col_s_app_v7 in required_cols_s_app_v7:
                if col_s_app_v7 not in df_s_app_v7.columns:
                    st.error(f"'학생목록' 시트에 필수 열인 '{col_s_app_v7}'이(가) 없습니다. 확인해주세요.")
                    return pd.DataFrame()
        return df_s_app_v7
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("'학생목록' 스프레드시트를 찾을 수 없습니다. 이름을 확인하고 공유 설정을 점검하세요."); return pd.DataFrame()
    except Exception as e:
        st.error(f"학생 목록 로딩 중 오류(학생앱): {e}. '학생목록' 시트 내용을 확인하세요."); return pd.DataFrame()

def get_records_from_row2_header_s_app_v7(worksheet_s, expected_header_list_s):
    all_values_s_app_v7 = worksheet_s.get_all_values()
    if len(all_values_s_app_v7) < 2: return [] 
    data_rows_s_app_v7 = all_values_s_app_v7[2:]
    records_s_app_v7 = []
    for r_vals_s_app_v7 in data_rows_s_app_v7:
        rec_s_app_v7 = {}
        for i_s_app_v7, header_name_s_app_v7 in enumerate(expected_header_list_s):
            rec_s_app_v7[header_name_s_app_v7] = r_vals_s_app_v7[i_s_app_v7] if i_s_app_v7 < len(r_vals_s_app_v7) else None
        records_s_app_v7.append(rec_s_app_v7)
    return records_s_app_v7

def ensure_sheet_structure_s_app_v7(worksheet_to_ensure, settings_content_s, header_content_s):
    try:
        all_vals_ensure_s_v7 = worksheet_to_ensure.get_all_values()
        if not all_vals_ensure_s_v7: 
            worksheet_to_ensure.append_row(settings_content_s, value_input_option='USER_ENTERED')
            worksheet_to_ensure.append_row(header_content_s, value_input_option='USER_ENTERED'); return
        current_r1_s_v7 = all_vals_ensure_s_v7[0]
        if len(current_r1_s_v7) < 1 or current_r1_s_v7[0] != settings_content_s[0]: worksheet_to_ensure.update_cell(1, 1, settings_content_s[0])
        if len(current_r1_s_v7) < 2 or not current_r1_s_v7[1]: worksheet_to_ensure.update_cell(1, 2, settings_content_s[1])
        if len(all_vals_ensure_s_v7) < 2: worksheet_to_ensure.append_row(header_content_s, value_input_option='USER_ENTERED')
        else:
            current_r2_s_v7 = all_vals_ensure_s_v7[1]
            if list(current_r2_s_v7) != header_content_s:
                try: 
                    header_end_col_letter_v7 = chr(ord('A') + len(header_content_s) - 1)
                    range_header_s_v7 = f'A2:{header_end_col_letter_v7}2'
                    worksheet_to_ensure.update(range_header_s_v7, [header_content_s], value_input_option='USER_ENTERED')
                except Exception: pass 
    except Exception: pass

# --- 세션 상태 초기화 ---
default_session_states_s_app_v7 = { # 버전업
    "student_logged_in": False, "student_page": "login", "student_name": None, 
    "student_sheet_url": None, "student_emotion": None, "student_gratitude": "", 
    "student_message": "", "student_selected_diary_date": None,
    "student_navigation_history": [], 
    "student_all_entries_cache": None, 
    "student_new_notes_to_display": [], 
    "notes_check_outcome": None 
}
for key_s_v7, val_s_v7 in default_session_states_s_app_v7.items():
    if key_s_v7 not in st.session_state: st.session_state[key_s_v7] = val_s_v7

# --- 네비게이션 함수 (스택 활용) ---
def student_go_to_page_nav_v7(target_page_nav_s, **kwargs_nav):
    current_page_nav_s_v7 = st.session_state.student_page
    if current_page_nav_s_v7 != target_page_nav_s:
        if current_page_nav_s_v7 != "login": 
            if not st.session_state.student_navigation_history or st.session_state.student_navigation_history[-1] != current_page_nav_s_v7:
                st.session_state.student_navigation_history.append(current_page_nav_s_v7)
    
    for key_nav, value_nav in kwargs_nav.items(): 
        st.session_state[key_nav] = value_nav

    st.session_state.student_page = target_page_nav_s
    st.rerun()

def student_go_back_page_nav_v7():
    # ★★★ "뒤로가기" 시, 현재 페이지가 "check_notes"였다면 관련 상태 초기화 ★★★
    if st.session_state.student_page == "check_notes":
        st.session_state.notes_check_outcome = None
        st.session_state.student_new_notes_to_display = []

    if st.session_state.student_navigation_history:
        st.session_state.student_page = st.session_state.student_navigation_history.pop()
    else:
        st.session_state.student_page = "menu" 
    st.rerun()

def student_logout_nav_v7():
    for key_to_reset_nav_s_v7 in default_session_states_s_app_v7.keys():
        st.session_state[key_to_reset_nav_s_v7] = default_session_states_s_app_v7[key_to_reset_nav_s_v7]
    st.rerun()

# --- 학생 데이터 로드 및 캐시 함수 ---
def load_student_all_entries_cached_v7(g_client_s_app_v7, sheet_url_s_app_v7):
    if isinstance(st.session_state.student_all_entries_cache, pd.DataFrame):
        return st.session_state.student_all_entries_cache
    try:
        with st.spinner("학생 일기 데이터 로딩 중... (API 호출)"):
            ws_s_load_app_v7 = g_client_s_app_v7.open_by_url(sheet_url_s_app_v7).sheet1
            ensure_sheet_structure_s_app_v7(ws_s_load_app_v7, SETTINGS_ROW_DEFAULT, EXPECTED_STUDENT_SHEET_HEADER)
            records_s_load_app_v7 = get_records_from_row2_header_s_app_v7(ws_s_load_app_v7, EXPECTED_STUDENT_SHEET_HEADER)
            df_s_load_app_v7 = pd.DataFrame(records_s_load_app_v7)
            st.session_state.student_all_entries_cache = df_s_load_app_v7
            return df_s_load_app_v7
    except Exception as e_load_s_app_v7:
        st.error(f"학생 일기 데이터 로드 오류: {e_load_s_app_v7}"); return pd.DataFrame()

# --- MAIN STUDENT APP ---
g_client_student_main_v7 = authorize_gspread_student_final_v7()
students_df_login_v7 = get_students_df_for_student_app_v7(g_client_student_main_v7)

if st.session_state.student_page == "login":
    st.title("👧 감정 일기 로그인")
    s_name_in_v7 = st.text_input("이름", key="s_login_name_vfinal_7")
    s_pw_in_v7 = st.text_input("비밀번호 (6자리)", type="password", max_chars=6, key="s_login_pw_vfinal_7")

    if st.button("로그인", key="s_login_btn_vfinal_7"):
        s_name_login_v7, s_pw_login_v7 = s_name_in_v7.strip(), s_pw_in_v7.strip()
        if not s_name_login_v7 or not s_pw_login_v7: st.warning("이름과 비밀번호를 모두 입력하세요.")
        else:
            if students_df_login_v7.empty and g_client_student_main_v7:
                 st.error("'학생목록' 시트가 비었거나 접근할 수 없습니다. 관리자에게 문의하세요.")
            elif students_df_login_v7.empty and not g_client_student_main_v7: 
                 st.error("Google API 인증에 실패했습니다. secrets 설정을 확인하거나 관리자에게 문의하세요.")
            else:
                s_record_v7 = students_df_login_v7[students_df_login_v7["이름"] == s_name_login_v7]
                if not s_record_v7.empty and str(s_record_v7.iloc[0]["비밀번호"]).strip() == s_pw_login_v7:
                    for key_s_reset_v7, val_s_reset_v7 in default_session_states_s_app_v7.items():
                        st.session_state[key_s_reset_v7] = val_s_reset_v7
                    st.session_state.student_logged_in = True
                    st.session_state.student_name = s_name_login_v7
                    st.session_state.student_sheet_url = s_record_v7.iloc[0]["시트URL"]
                    student_go_to_page_nav_v7("check_notes", notes_check_outcome=None, student_new_notes_to_display=[])
                else: st.error("이름 또는 비밀번호가 틀립니다.")

elif st.session_state.student_logged_in:
    df_student_entries_main_v7 = load_student_all_entries_cached_v7(g_client_student_main_v7, st.session_state.student_sheet_url)

    if st.session_state.student_page == "check_notes":
        st.title(f"📬 {st.session_state.student_name}님, 선생님 쪽지 확인")
        
        if st.session_state.notes_check_outcome is None: # 버튼 클릭 전 초기 상태
            st.info("아래 '새로운 선생님 쪽지 확인하기 🔍' 버튼을 눌러 새 쪽지가 있는지 확인해보세요.")

        if st.button("새로운 선생님 쪽지 확인하기 🔍", key="s_check_new_notes_btn_vfinal_7"):
            new_notes_this_check_v7 = [] 
            with st.spinner("새로운 쪽지를 확인하는 중입니다... (API 호출 중)"):
                try:
                    student_sheet_url_notes_v7 = st.session_state.student_sheet_url
                    if not student_sheet_url_notes_v7:
                        st.error("학생 시트 정보를 찾을 수 없습니다."); st.stop()

                    ws_notes_v7 = g_client_student_main_v7.open_by_url(student_sheet_url_notes_v7).sheet1
                    ensure_sheet_structure_s_app_v7(ws_notes_v7, SETTINGS_ROW_DEFAULT, EXPECTED_STUDENT_SHEET_HEADER)
                    
                    last_checked_date_str_v7 = "2000-01-01"
                    try:
                        b1_val_v7 = ws_notes_v7.cell(1, 2).value
                        if b1_val_v7: last_checked_date_str_v7 = b1_val_v7
                    except Exception: pass 
                    
                    if not df_student_entries_main_v7.empty:
                        try: last_checked_dt_v7 = datetime.strptime(last_checked_date_str_v7, "%Y-%m-%d").date()
                        except ValueError: last_checked_dt_v7 = datetime.strptime("2000-01-01", "%Y-%m-%d").date()

                        for _, row_n_v7 in df_student_entries_main_v7.iterrows():
                            date_n_v7, note_n_v7 = row_n_v7.get("날짜"), str(row_n_v7.get("선생님 쪽지", "")).strip()
                            if note_n_v7 and date_n_v7:
                                try:
                                    if datetime.strptime(date_n_v7, "%Y-%m-%d").date() > last_checked_dt_v7:
                                        new_notes_this_check_v7.append((date_n_v7, note_n_v7))
                                except ValueError: continue                         
                        
                        update_b1_date_v7 = datetime.today().strftime("%Y-%m-%d")
                        if new_notes_this_check_v7: update_b1_date_v7 = new_notes_this_check_v7[-1][0]
                        
                        try: ws_notes_v7.update_cell(1, 2, update_b1_date_v7)
                        except Exception as e_b1: st.warning(f"확인 날짜 업데이트 실패: {e_b1}")
                    else: st.warning("일기 데이터가 없습니다.")

                    if new_notes_this_check_v7:
                        st.session_state.student_new_notes_to_display = sorted(new_notes_this_check_v7, key=lambda x: x[0])
                        st.session_state.notes_check_outcome = "NOTES_FOUND"
                    else:
                        st.session_state.student_new_notes_to_display = []
                        st.session_state.notes_check_outcome = "NO_NEW_NOTES"
                except Exception as e_notes: 
                    st.error(f"쪽지 확인 오류: {e_notes}")
                    st.session_state.notes_check_outcome = "ERROR"
            st.rerun() 

        if st.session_state.notes_check_outcome == "NOTES_FOUND":
            st.success(f"새로운 쪽지가 {len(st.session_state.student_new_notes_to_display)}개 도착했어요!")
            for date_d_v7, note_d_v7 in st.session_state.student_new_notes_to_display:
                st.markdown(f"**{date_d_v7}**: {note_d_v7}")
        elif st.session_state.notes_check_outcome == "NO_NEW_NOTES":
            st.info("새로운 선생님 쪽지가 없습니다.")
        elif st.session_state.notes_check_outcome == "ERROR":
            st.warning("쪽지를 확인하는 중 오류가 발생했습니다. 다시 시도해주세요.")
        
        st.divider()
        s_notes_cols1_v7, s_notes_cols2_v7 = st.columns(2)
        with s_notes_cols1_v7:
            if st.button("메인 메뉴", key="s_notes_to_menu_vfinal_7", use_container_width=True):
                student_go_to_page_nav_v7("menu", notes_check_outcome=None, student_new_notes_to_display=[])
        with s_notes_cols2_v7:
            if st.button("로그아웃", key="s_logout_notes_vfinal_7", use_container_width=True): student_logout_nav_v7()

    elif st.session_state.student_page == "menu":
        st.title(f"📘 {st.session_state.student_name}님 감정일기"); st.divider()
        if st.button("✏️ 오늘 일기 쓰기/수정", type="primary", use_container_width=True, key="s_menu_write_v7"):
            today_s_menu_v7 = datetime.today().strftime("%Y-%m-%d")
            st.session_state.student_emotion, st.session_state.student_gratitude, st.session_state.student_message = None, "", ""
            if not df_student_entries_main_v7.empty:
                today_entry_menu_v7 = df_student_entries_main_v7[df_student_entries_main_v7["날짜"] == today_s_menu_v7]
                if not today_entry_menu_v7.empty:
                    r_menu_v7 = today_entry_menu_v7.iloc[0]
                    st.session_state.student_emotion = r_menu_v7.get("감정")
                    st.session_state.student_gratitude = r_menu_v7.get("감사한 일", "")
                    st.session_state.student_message = r_menu_v7.get("하고 싶은 말", "")
            student_go_to_page_nav_v7("write_emotion")
        
        if st.button("지난 일기 보기/삭제", use_container_width=True, key="s_menu_view_v7"):
            student_go_to_page_nav_v7("view_modify_diary", student_selected_diary_date=None)
        if st.button("새로운 선생님 쪽지 확인", use_container_width=True, key="s_menu_notes_v7"):
            student_go_to_page_nav_v7("check_notes", notes_check_outcome=None, student_new_notes_to_display=[])
        if st.button("로그아웃", use_container_width=True, key="s_logout_menu_v7"): student_logout_nav_v7()
    
    # --- 이하 write_emotion, write_gratitude, write_message, confirm_submission 페이지 ---
    elif st.session_state.student_page == "write_emotion":
        st.title("😊 오늘의 감정"); st.caption("오늘 어떤 감정을 느꼈나요?")
        emo_dict_s_v7 = { "😀 긍정": ["기쁨", "감사", "자신감", "설렘", "평온"], "😐 보통": ["그냥 그래요", "지루함", "무난함"], "😢 부정": ["슬픔", "불안", "짜증", "화남", "피곤"] }
        cur_g_v7, cur_d_v7 = None, None
        if st.session_state.student_emotion:
            try: 
                g_v7, d_v7 = st.session_state.student_emotion.split(" - ",1)
                if g_v7 in emo_dict_s_v7 and d_v7 in emo_dict_s_v7[g_v7]: cur_g_v7, cur_d_v7 = g_v7, d_v7
            except ValueError: pass
        sel_g_v7 = st.selectbox("감정 그룹", list(emo_dict_s_v7.keys()), index=list(emo_dict_s_v7.keys()).index(cur_g_v7) if cur_g_v7 else 0, key="s_emo_g_vfinal_7")
        sel_d_v7 = st.selectbox("구체적 감정", emo_dict_s_v7[sel_g_v7], index=emo_dict_s_v7[sel_g_v7].index(cur_d_v7) if cur_d_v7 and cur_g_v7 == sel_g_v7 else 0, key="s_emo_d_vfinal_7")
        st.session_state.student_emotion = f"{sel_g_v7} - {sel_d_v7}"
        b1_we_v7,b2_we_v7 = st.columns(2)
        with b1_we_v7:
             if st.button("← 이전", key="s_emo_b_vfinal_7", use_container_width=True): student_go_back_page_nav_v7()
        with b2_we_v7:
            if st.button("다음 →", key="s_emo_n_vfinal_7", use_container_width=True, type="primary"): student_go_to_page_nav_v7("write_gratitude")

    elif st.session_state.student_page == "write_gratitude":
        st.title("🙏 감사한 일"); st.caption("오늘 어떤 점이 감사했나요?")
        st.session_state.student_gratitude = st.text_area("감사한 일", height=150, value=st.session_state.student_gratitude, key="s_grat_txt_vfinal_7", placeholder="사소한 것이라도 좋아요!")
        b1_wg_v7,b2_wg_v7 = st.columns(2)
        with b1_wg_v7:
            if st.button("← 이전", key="s_grat_b_vfinal_7", use_container_width=True): student_go_back_page_nav_v7()
        with b2_wg_v7:
            if st.button("다음 →", key="s_grat_n_vfinal_7", use_container_width=True, type="primary"): student_go_to_page_nav_v7("write_message")

    elif st.session_state.student_page == "write_message":
        st.title("💬 하고 싶은 말"); st.caption("선생님이나 친구, 또는 자신에게 하고 싶은 말을 자유롭게 적어보세요.")
        st.session_state.student_message = st.text_area("하고 싶은 말", height=200, value=st.session_state.student_message, key="s_msg_txt_vfinal_7", placeholder="어떤 이야기든 괜찮아요.")
        b1_wm_v7,b2_wm_v7 = st.columns(2)
        with b1_wm_v7:
            if st.button("← 이전", key="s_msg_b_vfinal_7", use_container_width=True): student_go_back_page_nav_v7()
        with b2_wm_v7:
            if st.button("다음 →", key="s_msg_n_vfinal_7", use_container_width=True, type="primary"): student_go_to_page_nav_v7("confirm_submission")

    elif st.session_state.student_page == "confirm_submission":
        st.title("✅ 내용 확인"); st.divider()
        st.write(f"**감정:** {st.session_state.student_emotion or '(선택 안 함)'}")
        st.write(f"**감사한 일:** {st.session_state.student_gratitude or '(내용 없음)'}")
        st.write(f"**하고 싶은 말:** {st.session_state.student_message or '(내용 없음)'}")
        st.divider()
        b1_cs_v7,b2_cs_v7 = st.columns(2)
        with b1_cs_v7:
            if st.button("← 수정하기", key="s_conf_b_vfinal_7", use_container_width=True): student_go_back_page_nav_v7()
        with b2_cs_v7:
            if st.button("✔️ 제출하기", key="s_submit_diary_vfinal_7", use_container_width=True, type="primary"):
                today_submit_s_v7 = datetime.today().strftime("%Y-%m-%d")
                try:
                    with st.spinner("일기 저장 중..."):
                        ws_s_submit_v7 = g_client_student_main_v7.open_by_url(st.session_state.student_sheet_url).sheet1
                        all_records_at_submit_v7 = get_records_from_row2_header_s_app_v7(ws_s_submit_v7, EXPECTED_STUDENT_SHEET_HEADER)
                        
                        existing_idx_s_v7, note_today_s_v7 = -1, ""
                        for idx_s_v7, r_s_submit_v7 in enumerate(all_records_at_submit_v7):
                            if r_s_submit_v7.get("날짜") == today_submit_s_v7:
                                existing_idx_s_v7, note_today_s_v7 = idx_s_v7, str(r_s_submit_v7.get("선생님 쪽지", "")); break
                        
                        new_data_s_v7 = [today_submit_s_v7, st.session_state.student_emotion,
                                          st.session_state.student_gratitude, st.session_state.student_message, note_today_s_v7]
                        
                        if existing_idx_s_v7 != -1: 
                            row_to_update_v7 = existing_idx_s_v7 + 3
                            end_col_letter_upd_v7 = chr(ord('A') + len(EXPECTED_STUDENT_SHEET_HEADER) - 1)
                            range_to_update_s_v7 = f'A{row_to_update_v7}:{end_col_letter_upd_v7}{row_to_update_v7}'
                            ws_s_submit_v7.update(range_to_update_s_v7, [new_data_s_v7], value_input_option='USER_ENTERED')
                            st.success("🔄 일기 수정 완료!")
                        else: 
                            ws_s_submit_v7.append_row(new_data_s_v7, value_input_option='USER_ENTERED')
                            st.success("🌟 일기 저장 완료!")
                        
                        st.session_state.student_all_entries_cache = None 
                        for k_form_s_v7 in ["student_emotion", "student_gratitude", "student_message"]: st.session_state[k_form_s_v7] = default_session_states_s_app_v7[k_form_s_v7]
                        st.session_state.student_selected_diary_date = today_submit_s_v7
                        st.session_state.student_navigation_history = [] 
                        st.balloons()
                        student_go_to_page_nav_v7("view_modify_diary", notes_check_outcome=None, student_new_notes_to_display=[])
                except Exception as e_s_v7: st.error(f"일기 저장 오류: {e_s_v7}")

    elif st.session_state.student_page == "view_modify_diary":
        st.title("📖 지난 일기 보기/삭제"); st.divider()
        if df_student_entries_main_v7.empty: st.info("작성된 일기가 없습니다.")
        else:
            dates_s_view_v7 = sorted(list(set(df_student_entries_main_v7["날짜"].dropna())), reverse=True)
            if not dates_s_view_v7: st.info("작성된 일기가 없습니다.")
            else:
                def_date_s_view_v7 = st.session_state.get("student_selected_diary_date")
                if not def_date_s_view_v7 or def_date_s_view_v7 not in dates_s_view_v7: def_date_s_view_v7 = dates_s_view_v7[0]
                
                sel_date_idx_v7 = dates_s_view_v7.index(def_date_s_view_v7) if def_date_s_view_v7 in dates_s_view_v7 else 0
                sel_date_s_v7 = st.selectbox("날짜 선택:", options=dates_s_view_v7, index=sel_date_idx_v7, key="s_diary_sel_vfinal_7")
                st.session_state.student_selected_diary_date = sel_date_s_v7

                diary_s_v7 = df_student_entries_main_v7[df_student_entries_main_v7["날짜"] == sel_date_s_v7]
                if not diary_s_v7.empty:
                    r_s_view_v7 = diary_s_v7.iloc[0]
                    st.subheader(f"🗓️ {sel_date_s_v7} 일기")
                    st.write(f"**감정:** {r_s_view_v7.get('감정', '')}")
                    st.write(f"**감사한 일:** {r_s_view_v7.get('감사한 일', '')}")
                    st.write(f"**하고 싶은 말:** {r_s_view_v7.get('하고 싶은 말', '')}")
                    st.write(f"**선생님 쪽지:** {str(r_s_view_v7.get('선생님 쪽지', ''))}")

                    delete_button_key_v7 = f"s_delete_btn_vfinal_7_{sel_date_s_v7.replace('-', '_')}"
                    if st.button(f"❌ {sel_date_s_v7} 일기 삭제", key=delete_button_key_v7, type="warning"):
                        try:
                            with st.spinner("일기 삭제 중..."):
                                ws_s_del_v7 = g_client_student_main_v7.open_by_url(st.session_state.student_sheet_url).sheet1
                                temp_recs_for_del_v7 = get_records_from_row2_header_s_app_v7(ws_s_del_v7, EXPECTED_STUDENT_SHEET_HEADER)
                                row_to_del_idx_v7 = -1
                                for idx_del_v7, r_del_v7 in enumerate(temp_recs_for_del_v7):
                                    if r_del_v7.get("날짜") == sel_date_s_v7: row_to_del_idx_v7 = idx_del_v7 + 3; break
                                
                                if row_to_del_idx_v7 != -1:
                                    ws_s_del_v7.delete_rows(row_to_del_idx_v7)
                                    st.session_state.student_all_entries_cache = None 
                                    st.success(f"✅ {sel_date_s_v7} 일기 삭제 완료.")
                                    st.session_state.student_selected_diary_date = None; st.rerun()
                                else: st.error("삭제할 일기를 시트에서 찾지 못했습니다.")
                        except Exception as e_s_del_v7: st.error(f"일기 삭제 오류: {e_s_del_v7}")
                else: st.info(f"{sel_date_s_v7}에 작성된 일기가 없습니다.")
        
        s_view_cols1_v7, s_view_cols2_v7 = st.columns(2)
        with s_view_cols1_v7:
            if st.button("뒤로가기", use_container_width=True, key="s_view_go_back_vfinal_7"): 
                student_go_back_page_nav_v7() # 스택 기반 뒤로가기
        with s_view_cols2_v7:
            if st.button("로그아웃", use_container_width=True, key="s_logout_view_vfinal_7"): student_logout_nav_v7()
else: 
    if st.session_state.student_page != "login": student_logout_nav_v7()
