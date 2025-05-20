import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# 페이지 기본 설정 (Page basic settings)
st.set_page_config(page_title="감정 일기장", page_icon="📘")

# --- 학생 시트 예상 헤더 ---
EXPECTED_STUDENT_SHEET_HEADER = ["날짜", "감정", "감사한 일", "하고 싶은 말", "선생님 쪽지"]

# --- Helper Function to Ensure Correct Sheet Header ---
def ensure_sheet_header(worksheet, expected_header):
    """
    Attempts to ensure the worksheet has the correct visual header row.
    This is a best-effort attempt for visual consistency.
    The main logic for data reading will rely on get_all_records(expected_headers=...).
    """
    try:
        current_header = []
        try:
            current_header = worksheet.row_values(1) # Get only the first row
        except gspread.exceptions.APIError as e:
            # Handle cases where the sheet might be too small or other API issues initially reading row 1
            st.warning(f"'{worksheet.title}' 시트의 첫 행을 읽는 중 문제 발생 (초기화 시도): {e}")
            # Proceed to check if sheet is completely empty or try to set header

        if not current_header and not worksheet.get_all_values(): # Sheet is completely empty
            worksheet.append_row(expected_header, value_input_option='USER_ENTERED')
            st.info(f"'{worksheet.title}' 시트가 비어있어 헤더를 새로 생성했습니다.")
        elif list(current_header) != expected_header: # Compare as list
            st.warning(f"'{worksheet.title}' 시트의 헤더가 예상과 다릅니다. 수정을 시도합니다. 현재: {current_header}, 예상: {expected_header}")
            try:
                # Define the range for the header, e.g., 'A1:E1'
                header_range = f'A1:{gspread.utils.rowcol_to_a1(1, len(expected_header))}'
                worksheet.update(header_range, [expected_header], value_input_option='USER_ENTERED')
                st.info(f"'{worksheet.title}' 시트의 헤더를 성공적으로 업데이트했습니다.")
            except Exception as update_e:
                st.error(f"'{worksheet.title}' 시트 헤더 업데이트 중 오류 발생: {update_e}. 프로그램은 예상 헤더를 사용하여 계속 진행합니다.")
        
    except gspread.exceptions.APIError as api_e:
        st.error(f"'{worksheet.title}' 시트 헤더 확인/수정 중 Google Sheets API 오류: {api_e}")
        # Do not raise further, allow get_all_records with expected_headers to try
    except Exception as e:
        st.error(f"'{worksheet.title}' 시트 헤더 확인/수정 중 예기치 않은 오류 발생: {e}")
        # Do not raise further

# --- Google Sheets API 인증 ---
try:
    credentials_dict = st.secrets["GOOGLE_CREDENTIALS"]
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
    client = gspread.authorize(creds)
except Exception as e:
    st.error(f"Google API 인증 중 오류가 발생했습니다: {e}")
    st.stop()

# --- 학생 목록 시트 불러오기 ---
try:
    student_list_ws = client.open("학생목록").sheet1
    # 학생 목록 시트 자체는 헤더가 고정적이라고 가정하고, 문제가 생기면 여기서 오류 발생
    students_df = pd.DataFrame(student_list_ws.get_all_records())
except gspread.exceptions.SpreadsheetNotFound:
    st.error("학생 목록 시트를 찾을 수 없습니다. Google Sheets에서 '학생목록' 시트가 정확히 있는지, 공유 설정이 올바른지 확인해주세요.")
    st.stop()
except Exception as e: # Catch other gspread or pandas errors
    st.error(f"학생 목록을 불러오는 중 오류가 발생했습니다: {e}. '학생목록' 시트의 헤더를 확인해주세요.")
    st.stop()

# --- 세션 상태 초기화 ---
defaults = {
    "logged_in": False, "page": "login", "name": None, "sheet_url": None,
    "emotion": None, "gratitude": "", "message": "", "new_notes": [],
    "new_notes_loaded": False, "b1_updated_this_visit": False
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ---------------------------
# 페이지: 로그인 (Page: Login)
# ---------------------------
if st.session_state.page == "login":
    st.title("👧 학생 감정일기 로그인")
    name_input = st.text_input("이름을 입력하세요", key="login_name")
    password_input = st.text_input("비밀번호 (6자리)", type="password", max_chars=6, key="login_password")

    if st.button("로그인", key="login_button"):
        name = name_input.strip()
        password = password_input.strip()
        if not name or not password:
            st.warning("이름과 비밀번호를 모두 입력해주세요.")
        else:
            student_record = students_df[students_df["이름"] == name]
            if not student_record.empty and str(student_record.iloc[0]["비밀번호"]).strip() == password:
                st.session_state.logged_in = True
                st.session_state.name = name
                st.session_state.sheet_url = student_record.iloc[0]["시트URL"]
                st.session_state.page = "check_notes"
                # Reset flags for the new session
                st.session_state.new_notes_loaded = False
                st.session_state.b1_updated_this_visit = False
                st.rerun() 
            else:
                st.error("이름 또는 비밀번호가 틀린 것 같습니다.")

# ---------------------------
# 페이지: 새로운 쪽지 확인 (Page: Check New Notes)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == "check_notes":
    st.title(f"📬 {st.session_state.name}님, 새로운 쪽지를 확인하세요")

    if not st.session_state.new_notes_loaded:
        try:
            student_ws = client.open_by_url(st.session_state.sheet_url).sheet1
            ensure_sheet_header(student_ws, EXPECTED_STUDENT_SHEET_HEADER) # Best-effort visual header fix

            last_checked_date_str = "2000-01-01"
            try:
                # A1: "설정", B1: last_checked_date
                cell_val_A1 = student_ws.cell(1, 1).value
                cell_val_B1 = student_ws.cell(1, 2).value
                if cell_val_A1 == "설정" and cell_val_B1:
                    last_checked_date_str = cell_val_B1
                else: # A1, B1이 없거나 내용이 다르면 초기화
                    student_ws.update('A1:B1', [["설정", "2000-01-01"]], value_input_option='USER_ENTERED')
            except gspread.exceptions.CellNotFound: # A1 또는 B1 셀 자체가 없는 경우
                 student_ws.update('A1:B1', [["설정", "2000-01-01"]], value_input_option='USER_ENTERED')
            
            # Use expected_headers to bypass issues with gspread's header auto-detection
            all_diary_entries = student_ws.get_all_records(expected_headers=EXPECTED_STUDENT_SHEET_HEADER)
            current_new_notes = []
            last_checked_dt_obj = datetime.strptime(last_checked_date_str, "%Y-%m-%d")

            for record in all_diary_entries:
                entry_date_str = record.get("날짜")
                teacher_note = str(record.get("선생님 쪽지", "")).strip()
                if teacher_note and entry_date_str:
                    try:
                        entry_dt_obj = datetime.strptime(entry_date_str, "%Y-%m-%d")
                        if entry_dt_obj > last_checked_dt_obj:
                            current_new_notes.append((entry_date_str, teacher_note))
                    except ValueError:
                        st.warning(f"일기 항목의 날짜('{entry_date_str}') 형식이 올바르지 않아 쪽지를 확인할 수 없습니다.")
            
            st.session_state.new_notes = sorted(current_new_notes, key=lambda x: x[0])
            st.session_state.new_notes_loaded = True

        except gspread.exceptions.APIError as e:
            st.error(f"새 쪽지 확인 중 Google Sheets API 오류: {e}")
            st.session_state.new_notes = []
        except Exception as e:
            st.error(f"새 쪽지를 확인하는 중 예기치 않은 오류가 발생했습니다: {e}")
            st.session_state.new_notes = [] # Ensure it's an empty list on error
            st.session_state.new_notes_loaded = True # Prevent reload loop on error
    
    # 쪽지 표시
    if st.session_state.new_notes:
        st.success(f"읽지 않은 쪽지가 {len(st.session_state.new_notes)}개 있어요!")
        for date_str, note_content in st.session_state.new_notes:
            st.markdown(f"**{date_str}**: {note_content}")
        
        if not st.session_state.b1_updated_this_visit:
            try:
                latest_note_date_to_save = st.session_state.new_notes[-1][0]
                student_ws_for_b1_update = client.open_by_url(st.session_state.sheet_url).sheet1
                student_ws_for_b1_update.update_cell(1, 2, latest_note_date_to_save) # Update B1
                st.info("모든 새 쪽지를 확인했습니다. 마지막 확인 날짜가 업데이트되었습니다.")
                st.session_state.b1_updated_this_visit = True 
            except Exception as e:
                st.error(f"마지막 확인 날짜 업데이트 중 오류: {e}")
    else:
        st.info("새로운 쪽지가 없습니다.")

    if st.button("메인 메뉴로 가기", key="goto_menu_from_notes"):
        st.session_state.page = "menu"
        st.session_state.new_notes_loaded = False 
        st.session_state.b1_updated_this_visit = False
        st.rerun()
    
    if st.button("로그아웃", key="logout_check_notes"):
        for key_to_reset in defaults.keys(): st.session_state[key_to_reset] = defaults[key_to_reset]
        st.rerun()

# ---------------------------
# 페이지: 메인 메뉴 (Page: Main Menu)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == "menu":
    st.title(f"📘 {st.session_state.name}님의 감정일기 메뉴")
    
    if st.button("✏️ 오늘 일기 쓰기", key="write_diary_button"):
        st.session_state.page = "write_emotion"
        st.rerun()
    
    if st.button("지난 일기 확인/삭제", key="view_past_diary_button"): # 새롭게 추가된 버튼
        st.session_state.page = "view_modify_diary"
        st.rerun()

    if st.button("로그아웃", key="logout_menu"):
        for key_to_reset in defaults.keys(): st.session_state[key_to_reset] = defaults[key_to_reset]
        st.rerun()

# ---------------------------
# 페이지: 감정 선택 (Page: Write Diary - Emotion)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == "write_emotion":
    st.title("오늘의 감정을 선택해주세요")
    emotion_dict = {
        "😀 긍정": ["기쁨", "감사", "자신감", "설렘", "평온"], 
        "😐 보통": ["그냥 그래요", "지루함", "무난함"], 
        "😢 부정": ["슬픔", "불안", "짜증", "화남", "피곤"]  
    }
    current_emotion_group, current_emotion_detail = None, None
    if st.session_state.emotion: # 이전에 선택한 값 복원 시도
        try:
            group_part, detail_part = st.session_state.emotion.split(" - ", 1)
            if group_part in emotion_dict and detail_part in emotion_dict[group_part]:
                current_emotion_group, current_emotion_detail = group_part, detail_part
        except ValueError: pass # 분리 실패 시 무시
    
    group_idx = list(emotion_dict.keys()).index(current_emotion_group) if current_emotion_group else 0
    group = st.selectbox("감정 그룹", list(emotion_dict.keys()), index=group_idx, key="emotion_group_select")
    
    detail_idx = emotion_dict[group].index(current_emotion_detail) if current_emotion_detail and current_emotion_group == group else 0
    detail = st.selectbox("구체적인 감정", emotion_dict[group], index=detail_idx, key="emotion_detail_select")
    st.session_state.emotion = f"{group} - {detail}"

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← 메인 메뉴", key="emotion_to_menu"): 
            st.session_state.page = "menu"
            st.rerun()
    with col_next:
        if st.button("다음: 감사한 일 →", key="emotion_to_gratitude"): 
            st.session_state.page = "write_gratitude"
            st.rerun()

# ---------------------------
# 페이지: 감사한 일 (Page: Write Diary - Gratitude)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == "write_gratitude":
    st.title("오늘 감사했던 일을 적어보세요")
    st.session_state.gratitude = st.text_area("감사한 일", height=150, value=st.session_state.gratitude, key="gratitude_text_area")

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← 이전: 감정 선택", key="gratitude_to_emotion"): 
            st.session_state.page = "write_emotion"
            st.rerun()
    with col_next:
        if st.button("다음: 하고 싶은 말 →", key="gratitude_to_message"): 
            st.session_state.page = "write_message"
            st.rerun()

# ---------------------------
# 페이지: 하고 싶은 말 (Page: Write Diary - Message)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == "write_message":
    st.title("선생님이나 친구에게 하고 싶은 말이 있나요?")
    st.session_state.message = st.text_area("하고 싶은 말", height=200, value=st.session_state.message, key="message_text_area") 

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← 이전: 감사한 일", key="message_to_gratitude"): 
            st.session_state.page = "write_gratitude"
            st.rerun()
    with col_next:
        if st.button("다음: 제출 전 확인 →", key="message_to_confirm"): 
            st.session_state.page = "confirm_submission"
            st.rerun()

# ---------------------------
# 페이지: 제출 확인 (Page: Write Diary - Confirm Submission)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == "confirm_submission":
    st.title("✅ 작성한 내용을 확인해주세요")
    st.write(f"**오늘의 감정:** {st.session_state.emotion}") 
    st.write(f"**감사한 일:** {st.session_state.gratitude}") 
    st.write(f"**하고 싶은 말:** {st.session_state.message}") 

    col_back, col_submit = st.columns(2)
    with col_back:
        if st.button("← 이전: 수정하기", key="confirm_to_message"): 
            st.session_state.page = "write_message" 
            st.rerun()
    with col_submit:
        if st.button("✔️ 제출하기", key="submit_diary_button"): 
            today_date_str = datetime.today().strftime("%Y-%m-%d")
            try:
                student_ws = client.open_by_url(st.session_state.sheet_url).sheet1
                ensure_sheet_header(student_ws, EXPECTED_STUDENT_SHEET_HEADER)
                
                records = student_ws.get_all_records(expected_headers=EXPECTED_STUDENT_SHEET_HEADER) 
                existing_row_index = -1
                note_for_today = "" 

                for idx, record in enumerate(records):
                    if record.get("날짜") == today_date_str:
                        existing_row_index = idx + 2 # gspread 행은 1부터 시작, 헤더 포함  
                        note_for_today = str(record.get("선생님 쪽지", ""))
                        break
                
                new_entry_data = [
                    today_date_str, st.session_state.emotion,
                    st.session_state.gratitude, st.session_state.message,
                    note_for_today 
                ]

                if existing_row_index != -1:
                    # 범위 업데이트 시 리스트의 리스트 형태로 전달
                    header_range = f'A{existing_row_index}:{gspread.utils.rowcol_to_a1(existing_row_index, len(EXPECTED_STUDENT_SHEET_HEADER))}'
                    student_ws.update(header_range, [new_entry_data], value_input_option='USER_ENTERED')
                    st.success("🔄 오늘의 일기가 성공적으로 수정되었습니다!") 
                else:
                    student_ws.append_row(new_entry_data, value_input_option='USER_ENTERED')
                    st.success("🌟 오늘의 일기가 성공적으로 저장되었습니다!") 
                
                st.balloons()
                st.session_state.emotion = None 
                st.session_state.gratitude = ""
                st.session_state.message = ""
                st.session_state.page = "view_modify_diary" # 제출 후 오늘 일기 확인 페이지로
                st.session_state.selected_diary_date = today_date_str # 오늘 날짜를 선택된 날짜로 전달
                st.rerun()

            except gspread.exceptions.APIError as e:
                 st.error(f"Google Sheets API 오류로 저장에 실패했습니다: {e}")
            except Exception as e:
                st.error(f"일기 저장 중 오류가 발생했습니다: {e}")

# ---------------------------
# 페이지: 지난 일기 확인 및 삭제 (Page: View/Modify Past Diary)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == "view_modify_diary":
    st.title("📖 일기 확인 및 삭제") 

    try:
        student_ws = client.open_by_url(st.session_state.sheet_url).sheet1
        ensure_sheet_header(student_ws, EXPECTED_STUDENT_SHEET_HEADER)
        records = student_ws.get_all_records(expected_headers=EXPECTED_STUDENT_SHEET_HEADER)
        
        # 날짜 선택 UI (오늘 날짜를 기본값으로)
        # st.session_state.selected_diary_date는 일기 제출 후 넘어올 때 설정됨
        available_dates = sorted(list(set(r.get("날짜") for r in records if r.get("날짜"))), reverse=True)
        
        # 이전에 선택된 날짜가 없거나, 현재 사용 가능한 날짜 목록에 없으면 오늘 날짜 또는 최신 날짜로 설정
        default_date_str = st.session_state.get("selected_diary_date", datetime.today().strftime("%Y-%m-%d"))
        if default_date_str not in available_dates and available_dates:
            default_date_str = available_dates[0] # 가장 최근 일기 날짜
        elif not available_dates: # 일기가 아예 없는 경우
             default_date_str = datetime.today().strftime("%Y-%m-%d")


        # 날짜 선택 박스 만들기 (available_dates가 비어있으면 오늘 날짜만 표시)
        if not available_dates:
            st.info("작성된 일기가 아직 없습니다.")
            selected_date_str = st.date_input("날짜를 선택하세요", value=datetime.strptime(default_date_str, "%Y-%m-%d"), disabled=True).strftime("%Y-%m-%d")
        else:
            selected_date_str = st.selectbox(
                "확인할 일기 날짜를 선택하세요:", 
                options=available_dates, 
                index=available_dates.index(default_date_str) if default_date_str in available_dates else 0,
                key="diary_date_selector"
            )
        st.session_state.selected_diary_date = selected_date_str # 선택된 날짜 저장


        found_diary_for_selected_date = False
        diary_to_display = None
        row_to_delete_idx = -1 # 0-based index for records list

        for idx, record in enumerate(records):
            if record.get("날짜") == selected_date_str:
                diary_to_display = record
                row_to_delete_idx = idx 
                found_diary_for_selected_date = True
                break 

        if found_diary_for_selected_date and diary_to_display:
            st.subheader(f"🗓️ {selected_date_str} 일기") 
            st.write(f"**감정:** {diary_to_display.get('감정', '기록 없음')}")
            st.write(f"**감사한 일:** {diary_to_display.get('감사한 일', '기록 없음')}")
            st.write(f"**하고 싶은 말:** {diary_to_display.get('하고 싶은 말', '기록 없음')}")
            st.write(f"**선생님 쪽지:** {str(diary_to_display.get('선생님 쪽지', '없음'))}") 

            if st.button(f"❌ {selected_date_str} 일기 삭제하기", key="delete_selected_diary_button"): 
                if row_to_delete_idx != -1:
                    # gspread 행은 1부터 시작, 헤더 포함이므로 (0-based_idx + 2)
                    student_ws.delete_rows(row_to_delete_idx + 2) 
                    st.success(f"✅ {selected_date_str} 일기를 삭제했어요.")
                    st.session_state.selected_diary_date = None # 선택된 날짜 초기화
                    st.rerun() # 페이지 새로고침하여 변경사항 반영
                else: 
                    st.error("삭제할 일기를 찾지 못했습니다. 새로고침 후 다시 시도해주세요.")
        elif available_dates : # 날짜는 선택 가능하지만 해당 날짜의 일기가 없는 경우 (삭제 직후 등)
             st.info(f"{selected_date_str}에 작성된 일기가 없습니다.")


    except gspread.exceptions.APIError as e:
        st.error(f"Google Sheets API 오류로 일기 확인에 실패했습니다: {e}")
    except Exception as e:
        st.error(f"일기를 확인하는 중 오류가 발생했습니다: {e}")

    if st.button("메인 메뉴로 돌아가기", key="view_diary_to_menu"): 
        st.session_state.page = "menu"
        st.session_state.selected_diary_date = None # 선택된 날짜 초기화
        st.rerun()
    
    if st.button("로그아웃", key="logout_view_diary"):
        for key_to_reset in defaults.keys(): st.session_state[key_to_reset] = defaults[key_to_reset]
        st.rerun()

# --- 로그인되지 않은 경우 또는 알 수 없는 페이지 상태 처리 ---
elif not st.session_state.logged_in and st.session_state.page != "login":
    for key_to_reset in defaults.keys(): 
        st.session_state[key_to_reset] = defaults[key_to_reset]
    st.session_state.page = "login" 
    st.rerun()
