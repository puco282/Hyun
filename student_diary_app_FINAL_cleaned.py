import streamlit as st
import pandas as pd
import gspread # gspread.utils는 필요시 gspread에서 자동으로 로드되는 경우가 많음
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
# from collections import deque # 큐는 이번 최종 버전에서 직접적인 UI 요소로 사용하지 않음

# --- 페이지 기본 설정 ---
st.set_page_config(page_title="감정 일기장 (학생용)", page_icon="📘", layout="centered")

# --- 학생 시트 예상 헤더 ---
EXPECTED_STUDENT_SHEET_HEADER = ["날짜", "감정", "감사한 일", "하고 싶은 말", "선생님 쪽지"]
SETTINGS_ROW_DEFAULT = ["설정", "2000-01-01"] # 학생 시트 B1셀 기본값 (마지막 쪽지 확인 날짜)

# --- Helper Functions ---
@st.cache_resource # 리소스 캐싱 (gspread 클라이언트 객체)
def authorize_gspread_student_final_v2(): # 함수 이름에 버전 표시
    try:
        credentials_dict_student_final_v2 = st.secrets["GOOGLE_CREDENTIALS"]
        scope_student_final_v2 = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds_student_final_v2 = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict_student_final_v2, scope_student_final_v2)
        client_gspread_student_final_v2 = gspread.authorize(creds_student_final_v2)
        return client_gspread_student_final_v2
    except Exception as e:
        st.error(f"Google API 인증 중 오류(학생앱): {e}. secrets 설정을 확인하세요."); st.stop(); return None

@st.cache_data(ttl=600) # 학생 목록은 10분간 캐시
def get_students_df_for_student_app_v2(_client_gspread_student):
    if not _client_gspread_student: return pd.DataFrame()
    try:
        student_list_ws_s_app_v2 = _client_gspread_student.open("학생목록").sheet1
        df_s_app_v2 = pd.DataFrame(student_list_ws_s_app_v2.get_all_records(head=1)) # 첫 행을 헤더로
        if not df_s_app_v2.empty:
            required_cols_s_app = ["이름", "비밀번호", "시트URL"]
            for col_s_app in required_cols_s_app:
                if col_s_app not in df_s_app_v2.columns:
                    st.error(f"'학생목록' 시트에 필수 열인 '{col_s_app}'이(가) 없습니다. 확인해주세요.")
                    return pd.DataFrame()
        return df_s_app_v2
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("'학생목록' 스프레드시트를 찾을 수 없습니다. 이름을 확인하고 공유 설정을 점검하세요."); return pd.DataFrame()
    except Exception as e:
        st.error(f"학생 목록 로딩 중 오류(학생앱): {e}. '학생목록' 시트 내용을 확인하세요."); return pd.DataFrame()

def get_records_from_row2_header_s_app_v2(worksheet_s, expected_header_list_s):
    all_values_s_app_v2 = worksheet_s.get_all_values()
    if len(all_values_s_app_v2) < 2: return [] 
    data_rows_s_app_v2 = all_values_s_app_v2[2:]
    records_s_app_v2 = []
    for r_vals_s_app_v2 in data_rows_s_app_v2:
        rec_s_app_v2 = {}
        for i_s_app_v2, header_name_s_app_v2 in enumerate(expected_header_list_s):
            rec_s_app_v2[header_name_s_app_v2] = r_vals_s_app_v2[i_s_app_v2] if i_s_app_v2 < len(r_vals_s_app_v2) else None
        records_s_app_v2.append(rec_s_app_v2)
    return records_s_app_v2

def ensure_sheet_structure_s_app_v2(worksheet_to_ensure, settings_content_s, header_content_s):
    try:
        all_vals_ensure_s_v2 = worksheet_to_ensure.get_all_values()
        if not all_vals_ensure_s_v2: 
            worksheet_to_ensure.append_row(settings_content_s, value_input_option='USER_ENTERED')
            worksheet_to_ensure.append_row(header_content_s, value_input_option='USER_ENTERED')
            return
        current_r1_s_v2 = all_vals_ensure_s_v2[0]
        if len(current_r1_s_v2) < 1 or current_r1_s_v2[0] != settings_content_s[0]: worksheet_to_ensure.update_cell(1, 1, settings_content_s[0])
        if len(current_r1_s_v2) < 2 or not current_r1_s_v2[1]: worksheet_to_ensure.update_cell(1, 2, settings_content_s[1])
        if len(all_vals_ensure_s_v2) < 2: worksheet_to_ensure.append_row(header_content_s, value_input_option='USER_ENTERED')
        else:
            current_r2_s_v2 = all_vals_ensure_s_v2[1]
            if list(current_r2_s_v2) != header_content_s:
                try: 
                    # gspread.utils.rowcol_to_a1 이 로드 안될 경우를 대비해 직접 계산 (E열까지 가정)
                    header_end_col_letter = chr(ord('A') + len(header_content_s) - 1)
                    range_header_s_v2 = f'A2:{header_end_col_letter}2'
                    worksheet_to_ensure.update(range_header_s_v2, [header_content_s], value_input_option='USER_ENTERED')
                except Exception: pass 
    except Exception: pass

# --- 세션 상태 초기화 ---
default_session_states_s_app_v2 = {
    "student_logged_in": False, "student_page": "login", "student_name": None, 
    "student_sheet_url": None, "student_emotion": None, "student_gratitude": "", 
    "student_message": "", "student_selected_diary_date": None,
    "student_navigation_history": [], 
    "student_all_entries_cache": None, 
    "student_new_notes_to_display": [], 
    "student_checked_notes_button_clicked": False 
}
for key_s_v2, val_s_v2 in default_session_states_s_app_v2.items():
    if key_s_v2 not in st.session_state:
        st.session_state[key_s_v2] = val_s_v2

# --- 네비게이션 함수 (스택 활용) ---
def student_go_to_page_nav_v2(target_page_nav_s):
    current_page_nav_s_v2 = st.session_state.student_page
    if current_page_nav_s_v2 != target_page_nav_s:
        if current_page_nav_s_v2 != "login": 
            if not st.session_state.student_navigation_history or st.session_state.student_navigation_history[-1] != current_page_nav_s_v2:
                st.session_state.student_navigation_history.append(current_page_nav_s_v2)
        st.session_state.student_page = target_page_nav_s
        st.rerun()

def student_go_back_page_nav_v2():
    if st.session_state.student_navigation_history:
        st.session_state.student_page = st.session_state.student_navigation_history.pop()
    else:
        st.session_state.student_page = "menu" 
    st.rerun()

def student_logout_nav_v2():
    for key_to_reset_nav_s_v2 in default_session_states_s_app_v2.keys():
        st.session_state[key_to_reset_nav_s_v2] = default_session_states_s_app_v2[key_to_reset_nav_s_v2]
    st.rerun()

# --- 학생 데이터 로드 및 캐시 함수 ---
def load_student_all_entries_cached_v2(g_client_s_app_v2, sheet_url_s_app_v2):
    if st.session_state.student_all_entries_cache is not None:
        return st.session_state.student_all_entries_cache, True 
    try:
        with st.spinner("학생 일기 데이터 로딩 중... (API 호출)"):
            ws_s_load_app_v2 = g_client_s_app_v2.open_by_url(sheet_url_s_app_v2).sheet1
            ensure_sheet_structure_s_app_v2(ws_s_load_app_v2, SETTINGS_ROW_DEFAULT, EXPECTED_STUDENT_SHEET_HEADER)
            records_s_load_app_v2 = get_records_from_row2_header_s_app_v2(ws_s_load_app_v2, EXPECTED_STUDENT_SHEET_HEADER)
            df_s_load_app_v2 = pd.DataFrame(records_s_load_app_v2)
            st.session_state.student_all_entries_cache = df_s_load_app_v2
            return df_s_load_app_v2, False
    except Exception as e_load_s_app_v2:
        st.error(f"학생 일기 데이터 로드 오류: {e_load_s_app_v2}"); return pd.DataFrame(), False

# --- MAIN STUDENT APP ---
g_client_student_main_v2 = authorize_gspread_student_final_v2()
students_df_login_v2 = get_students_df_for_student_app_v2(g_client_student_main_v2)

if st.session_state.student_page == "login":
    st.title("👧 감정 일기 로그인")
    s_name_in_v2 = st.text_input("이름", key="s_login_name_vfinal_2")
    s_pw_in_v2 = st.text_input("비밀번호 (6자리)", type="password", max_chars=6, key="s_login_pw_vfinal_2")

    if st.button("로그인", key="s_login_btn_vfinal_2"):
        s_name_login_v2, s_pw_login_v2 = s_name_in_v2.strip(), s_pw_in_v2.strip()
        if not s_name_login_v2 or not s_pw_login_v2: st.warning("이름과 비밀번호를 모두 입력하세요.")
        else:
            if students_df_login_v2.empty and g_client_student_main_v2:
                 st.error("'학생목록' 시트가 비었거나 접근할 수 없습니다. 관리자에게 문의하세요.")
            elif students_df_login_v2.empty and not g_client_student_main_v2: # g_client 인증 자체가 실패한 경우
                 st.error("Google API 인증에 실패했습니다. secrets 설정을 확인하거나 관리자에게 문의하세요.")
            else:
                s_record_v2 = students_df_login_v2[students_df_login_v2["이름"] == s_name_login_v2]
                if not s_record_v2.empty and str(s_record_v2.iloc[0]["비밀번호"]).strip() == s_pw_login_v2:
                    for key_s_reset_v2, val_s_reset_v2 in default_session_states_s_app_v2.items():
                        st.session_state[key_s_reset_v2] = val_s_reset_v2
                    st.session_state.student_logged_in = True
                    st.session_state.student_name = s_name_login_v2
                    st.session_state.student_sheet_url = s_record_v2.iloc[0]["시트URL"]
                    student_go_to_page_nav_v2("check_notes") 
                else: st.error("이름 또는 비밀번호가 틀립니다.")

elif st.session_state.student_logged_in:
    # 학생의 전체 일기 데이터 로드 (캐시 활용)
    # 이 df_student_entries_main_v2는 해당 학생의 세션 동안 유지되며, 각 페이지에서 활용됩니다.
    df_student_entries_main_v2, _ = load_student_all_entries_cached_v2(g_client_student_main_v2, st.session_state.student_sheet_url)

    if st.session_state.student_page == "check_notes":
        st.title(f"📬 {st.session_state.student_name}님, 선생님 쪽지 확인")
        st.markdown("아래 버튼을 눌러 새 쪽지가 있는지 확인하세요.")

        if st.button("새로운 선생님 쪽지 확인하기 🔍", key="s_check_new_notes_btn_vfinal_2"):
            st.session_state.student_new_notes_to_display = [] 
            st.session_state.student_checked_notes_button_clicked = True
            
            with st.spinner("새로운 쪽지를 확인하는 중입니다... (API 호출 중)"):
                try:
                    student_sheet_url_for_notes_v2 = st.session_state.student_sheet_url
                    if not student_sheet_url_for_notes_v2: # 시트 URL이 없는 비정상적 상황 방어
                        st.error("학생 시트 정보를 찾을 수 없습니다. 다시 로그인해주세요."); st.stop()

                    ws_notes_check_final_v2 = g_client_student_main_v2.open_by_url(student_sheet_url_for_notes_v2).sheet1
                    ensure_sheet_structure_s_app_v2(ws_notes_check_final_v2, SETTINGS_ROW_DEFAULT, EXPECTED_STUDENT_SHEET_HEADER)
                    
                    last_checked_date_str_s_final_v2 = "2000-01-01"
                    try:
                        b1_val_s_final_v2 = ws_notes_check_final_v2.cell(1, 2).value
                        if b1_val_s_final_v2: last_checked_date_str_s_final_v2 = b1_val_s_final_v2
                    except Exception: st.caption("마지막 확인 날짜 정보 로드 실패 (기본값 사용)")
                    
                    if not df_student_entries_main_v2.empty:
                        new_notes_found_list_final_v2 = []
                        try: last_checked_dt_s_final_v2 = datetime.strptime(last_checked_date_str_s_final_v2, "%Y-%m-%d").date()
                        except ValueError: last_checked_dt_s_final_v2 = datetime.strptime("2000-01-01", "%Y-%m-%d").date()

                        for _, row_note_final_v2 in df_student_entries_main_v2.iterrows():
                            entry_date_str_final_v2 = row_note_final_v2.get("날짜")
                            teacher_note_final_v2 = str(row_note_final_v2.get("선생님 쪽지", "")).strip()
                            if teacher_note_final_v2 and entry_date_str_final_v2:
                                try:
                                    entry_dt_final_v2 = datetime.strptime(entry_date_str_final_v2, "%Y-%m-%d").date()
                                    if entry_dt_final_v2 > last_checked_dt_s_final_v2:
                                        new_notes_found_list_final_v2.append((entry_date_str_final_v2, teacher_note_final_v2))
                                except ValueError: continue 
                        
                        st.session_state.student_new_notes_to_display = sorted(new_notes_found_list_final_v2, key=lambda x: x[0])
                        
                        update_b1_date_final_v2 = datetime.today().strftime("%Y-%m-%d")
                        if new_notes_found_list_final_v2: update_b1_date_final_v2 = new_notes_found_list_final_v2[-1][0]
                        
                        try: ws_notes_check_final_v2.update_cell(1, 2, update_b1_date_final_v2)
                        except Exception as e_b1_update_v2: st.warning(f"마지막 확인 날짜 업데이트 실패: {e_b1_update_v2}")
                    else: st.warning("일기 데이터가 없습니다. 먼저 일기를 작성해주세요.")
                except gspread.exceptions.APIError as e_api_s_notes_v2:
                    st.error(f"Google API 오류로 쪽지 확인 실패 (코드: {e_api_s_notes_v2.response.status_code}). 잠시 후 다시 시도.")
                except Exception as e_s_notes_final_v2:
                    st.error(f"쪽지 확인 중 오류: {e_s_notes_final_v2}")
                    st.session_state.student_checked_notes_button_clicked = False

        if st.session_state.student_checked_notes_button_clicked:
            if st.session_state.student_new_notes_to_display:
                st.success(f"새로운 쪽지 {len(st.session_state.student_new_notes_to_display)}개 도착!")
                for date_display_final_v2, note_display_final_v2 in st.session_state.student_new_notes_to_display:
                    st.markdown(f"**{date_display_final_v2}**: {note_display_final_v2}")
            else:
                st.info("새로운 선생님 쪽지가 없습니다.") # 버튼 클릭 후 결과
        else:
            st.info("위의 '새로운 선생님 쪽지 확인하기 🔍' 버튼을 눌러주세요.") # 버튼 클릭 전 안내
        
        st.divider()
        s_notes_page_col1_v2, s_notes_page_col2_v2 = st.columns(2)
        with s_notes_page_col1_v2:
            if st.button("메인 메뉴", key="s_check_notes_to_menu_btn_vfinal_2", use_container_width=True):
                student_go_to_page_nav_v2("menu") 
        with s_notes_page_col2_v2:
            if st.button("로그아웃", key="s_logout_btn_check_notes_page_vfinal_2", use_container_width=True):
                student_logout_nav_v2()

    elif st.session_state.student_page == "menu":
        st.title(f"📘 {st.session_state.student_name}님 감정일기"); st.divider()
        # ... (메뉴 페이지 버튼들 - 이전 코드와 동일하게 student_go_to_page_nav_v2 사용) ...
        if st.button("✏️ 오늘 일기 쓰기/수정", type="primary", use_container_width=True, key="s_menu_to_write_vfinal_2"):
            today_s_v2 = datetime.today().strftime("%Y-%m-%d")
            st.session_state.student_emotion, st.session_state.student_gratitude, st.session_state.student_message = None, "", ""
            if not df_student_entries_main_v2.empty:
                today_e_v2 = df_student_entries_main_v2[df_student_entries_main_v2["날짜"] == today_s_v2]
                if not today_e_v2.empty:
                    r_v2 = today_e_v2.iloc[0]
                    st.session_state.student_emotion, st.session_state.student_gratitude, st.session_state.student_message = r_v2.get("감정"), r_v2.get("감사한 일", ""), r_v2.get("하고 싶은 말", "")
            student_go_to_page_nav_v2("write_emotion")
        
        if st.button("지난 일기 보기/삭제", use_container_width=True, key="s_menu_to_view_vfinal_2"):
            st.session_state.student_selected_diary_date = None; student_go_to_page_nav_v2("view_modify_diary")
        if st.button("새로운 선생님 쪽지 확인", use_container_width=True, key="s_menu_to_notes_vfinal_2"):
            st.session_state.student_checked_notes_button_clicked = False # ★★★ 중요: 쪽지확인 페이지로 갈 때 플래그 리셋
            st.session_state.student_new_notes_to_display = []
            student_go_to_page_nav_v2("check_notes")
        if st.button("로그아웃", use_container_width=True, key="s_logout_menu_vfinal_2"): student_logout_nav_v2()


    elif st.session_state.student_page == "write_emotion":
        st.title("😊 오늘의 감정"); st.caption("오늘 어떤 감정을 느꼈나요?")
        # ... (감정 선택 로직은 이전과 동일) ...
        emo_dict_s_v2 = { "😀 긍정": ["기쁨", "감사", "자신감", "설렘", "평온"], "😐 보통": ["그냥 그래요", "지루함", "무난함"], "😢 부정": ["슬픔", "불안", "짜증", "화남", "피곤"] }
        cur_g_v2, cur_d_v2 = None, None
        if st.session_state.student_emotion:
            try: g_v2, d_v2 = st.session_state.student_emotion.split(" - ",1);_ =0
            except ValueError: pass
            if g_v2 in emo_dict_s_v2 and d_v2 in emo_dict_s_v2[g_v2]: cur_g_v2, cur_d_v2 = g_v2, d_v2
        sel_g_v2 = st.selectbox("감정 그룹", list(emo_dict_s_v2.keys()), index=list(emo_dict_s_v2.keys()).index(cur_g_v2) if cur_g_v2 else 0, key="s_emo_g_vfinal_2")
        sel_d_v2 = st.selectbox("구체적 감정", emo_dict_s_v2[sel_g_v2], index=emo_dict_s_v2[sel_g_v2].index(cur_d_v2) if cur_d_v2 and cur_g_v2 == sel_g_v2 else 0, key="s_emo_d_vfinal_2")
        st.session_state.student_emotion = f"{sel_g_v2} - {sel_d_v2}"
        b1_we,b2_we = st.columns(2);b1_we.button("← 이전", on_click=student_go_back_page_nav_v2, key="s_emo_b_vfinal_2", use_container_width=True);b2_we.button("다음 →", on_click=student_go_to_page_nav_v2, args=("write_gratitude",), key="s_emo_n_vfinal_2", use_container_width=True, type="primary")

    elif st.session_state.student_page == "write_gratitude":
        st.title("🙏 감사한 일"); st.caption("오늘 어떤 점이 감사했나요?")
        st.session_state.student_gratitude = st.text_area("감사한 일", height=150, value=st.session_state.student_gratitude, key="s_grat_txt_vfinal_2", placeholder="사소한 것이라도 좋아요!")
        b1_wg,b2_wg = st.columns(2);b1_wg.button("← 이전", on_click=student_go_back_page_nav_v2, key="s_grat_b_vfinal_2", use_container_width=True);b2_wg.button("다음 →", on_click=student_go_to_page_nav_v2, args=("write_message",), key="s_grat_n_vfinal_2", use_container_width=True, type="primary")

    elif st.session_state.student_page == "write_message":
        st.title("💬 하고 싶은 말"); st.caption("선생님이나 친구, 또는 자신에게 하고 싶은 말을 자유롭게 적어보세요.")
        st.session_state.student_message = st.text_area("하고 싶은 말", height=200, value=st.session_state.student_message, key="s_msg_txt_vfinal_2", placeholder="어떤 이야기든 괜찮아요.")
        b1_wm,b2_wm = st.columns(2);b1_wm.button("← 이전", on_click=student_go_back_page_nav_v2, key="s_msg_b_vfinal_2", use_container_width=True);b2_wm.button("다음 →", on_click=student_go_to_page_nav_v2, args=("confirm_submission",), key="s_msg_n_vfinal_2", use_container_width=True, type="primary")

    elif st.session_state.student_page == "confirm_submission":
        st.title("✅ 내용 확인"); st.divider()
        # ... (제출 확인 페이지 버튼 및 로직은 이전과 동일, 네비게이션 함수 사용) ...
        st.write(f"**감정:** {st.session_state.student_emotion or '(선택 안 함)'}")
        st.write(f"**감사한 일:** {st.session_state.student_gratitude or '(내용 없음)'}")
        st.write(f"**하고 싶은 말:** {st.session_state.student_message or '(내용 없음)'}")
        st.divider()
        b1_cs,b2_cs = st.columns(2);b1_cs.button("← 수정하기", on_click=student_go_back_page_nav_v2, key="s_conf_b_vfinal_2", use_container_width=True)
        if b2_cs.button("✔️ 제출하기", key="s_submit_diary_vfinal_2", use_container_width=True, type="primary"):
            today_submit_s_v2 = datetime.today().strftime("%Y-%m-%d")
            try:
                with st.spinner("일기 저장 중..."):
                    ws_s_submit_v2 = g_client_student_main_v2.open_by_url(st.session_state.student_sheet_url).sheet1
                    # 저장 시점의 정확한 행 인덱스를 위해 전체 레코드 다시 로드 (또는 캐시된 리스트 활용)
                    all_records_at_submit = get_records_from_row2_header_s_app_v2(ws_s_submit_v2, EXPECTED_STUDENT_SHEET_HEADER)
                    
                    existing_idx_s_v2, note_today_s_v2 = -1, ""
                    for idx_s, r_s_submit_v2 in enumerate(all_records_at_submit):
                        if r_s_submit_v2.get("날짜") == today_submit_s_v2:
                            existing_idx_s_v2, note_today_s_v2 = idx_s, str(r_s_submit_v2.get("선생님 쪽지", "")); break
                    
                    new_data_s_v2 = [today_submit_s_v2, st.session_state.student_emotion,
                                      st.session_state.student_gratitude, st.session_state.student_message, note_today_s_v2]
                    
                    if existing_idx_s_v2 != -1:
                        row_to_update_v2 = existing_idx_s_v2 + 3
                        # gspread.utils.rowcol_to_a1 이 로드 안될 경우를 대비해 직접 계산
                        end_col_letter_update = chr(ord('A') + len(EXPECTED_STUDENT_SHEET_HEADER) - 1)
                        range_to_update_s_v2 = f'A{row_to_update_v2}:{end_col_letter_update}{row_to_update_v2}'
                        ws_s_submit_v2.update(range_to_update_s_v2, [new_data_s_v2], value_input_option='USER_ENTERED')
                        st.success("🔄 일기 수정 완료!")
                    else: 
                        ws_s_submit_v2.append_row(new_data_s_v2, value_input_option='USER_ENTERED')
                        st.success("🌟 일기 저장 완료!")
                    
                    st.session_state.student_all_entries_cache = None # 캐시 무효화
                    for k_form_s in ["student_emotion", "student_gratitude", "student_message"]: st.session_state[k_form_s] = default_session_states_s_app_v2[k_form_s]
                    st.session_state.student_selected_diary_date = today_submit_s_v2
                    st.session_state.student_navigation_history = [] 
                    st.balloons(); student_go_to_page_nav_v2("view_modify_diary")
            except Exception as e_s_v2: st.error(f"일기 저장 오류: {e_s_v2}")

    elif st.session_state.student_page == "view_modify_diary":
        st.title("📖 지난 일기 보기/삭제"); st.divider()
        # ... (지난 일기 보기/삭제 페이지 버튼 및 로직은 이전과 동일, 네비게이션 함수 사용) ...
        if df_student_entries_main_v2.empty: st.info("작성된 일기가 없습니다.")
        else:
            dates_s_view_v2 = sorted(list(set(df_student_entries_main_v2["날짜"].dropna())), reverse=True)
            if not dates_s_view_v2: st.info("작성된 일기가 없습니다.")
            else:
                def_date_s_view_v2 = st.session_state.get("student_selected_diary_date")
                if not def_date_s_view_v2 or def_date_s_view_v2 not in dates_s_view_v2: def_date_s_view_v2 = dates_s_view_v2[0]
                
                sel_date_idx_v2 = dates_s_view_v2.index(def_date_s_view_v2) if def_date_s_view_v2 in dates_s_view_v2 else 0
                sel_date_s_v2 = st.selectbox("날짜 선택:", options=dates_s_view_v2, index=sel_date_idx_v2, key="s_diary_sel_vfinal_2")
                st.session_state.student_selected_diary_date = sel_date_s_v2

                diary_s_v2 = df_student_entries_main_v2[df_student_entries_main_v2["날짜"] == sel_date_s_v2]
                if not diary_s_v2.empty:
                    r_s_view_v2 = diary_s_v2.iloc[0]
                    st.subheader(f"🗓️ {sel_date_s_v2} 일기")
                    st.write(f"**감정:** {r_s_view_v2.get('감정', '')}")
                    st.write(f"**감사한 일:** {r_s_view_v2.get('감사한 일', '')}")
                    st.write(f"**하고 싶은 말:** {r_s_view_v2.get('하고 싶은 말', '')}")
                    st.write(f"**선생님 쪽지:** {str(r_s_view_v2.get('선생님 쪽지', ''))}")

                    if st.button(f"❌ {sel_date_s_v2} 일기 삭제", key="s_delete_btn_vfinal_2", type="warning"):
                        try:
                            with st.spinner("일기 삭제 중..."):
                                ws_s_del_v2 = g_client_student_main_v2.open_by_url(st.session_state.student_sheet_url).sheet1
                                # 삭제 시 정확한 행 번호를 위해 다시 읽거나, 캐시된 원본 리스트 사용 필요
                                temp_recs_for_del_v2 = get_records_from_row2_header_s_app_v2(ws_s_del_v2, EXPECTED_STUDENT_SHEET_HEADER)
                                row_to_del_idx_v2 = -1
                                for idx_del_v2, r_del_v2 in enumerate(temp_recs_for_del_v2):
                                    if r_del_v2.get("날짜") == sel_date_s_v2: row_to_del_idx_v2 = idx_del_v2 + 3; break
                                
                                if row_to_del_idx_v2 != -1:
                                    ws_s_del_v2.delete_rows(row_to_del_idx_v2)
                                    st.session_state.student_all_entries_cache = None 
                                    st.success(f"✅ {sel_date_s_v2} 일기 삭제 완료.")
                                    st.session_state.student_selected_diary_date = None; st.rerun()
                                else: st.error("삭제할 일기를 시트에서 찾지 못했습니다.")
                        except Exception as e_s_del_v2: st.error(f"일기 삭제 오류: {e_s_del_v2}")
                else: st.info(f"{sel_date_s_v2}에 작성된 일기가 없습니다.")
        
        s_view_cols1_v2, s_view_cols2_v2 = st.columns(2)
        with s_view_cols1_v2:
            if st.button("메인 메뉴", use_container_width=True, key="s_view_to_menu_vfinal_2"): student_go_to_page_nav_v2("menu")
        with s_view_cols2_v2:
            if st.button("로그아웃", use_container_width=True, key="s_logout_view_vfinal_2"): student_logout_nav_v2()
else: 
    if st.session_state.student_page != "login": student_logout_nav_v2()
