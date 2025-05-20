import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# 페이지 기본 설정 (Page basic settings)
st.set_page_config(page_title="감정 일기장", page_icon="📘")

# --- 학생 시트 예상 헤더 (두 번째 행에 위치) ---
EXPECTED_STUDENT_SHEET_HEADER = ["날짜", "감정", "감사한 일", "하고 싶은 말", "선생님 쪽지"]
SETTINGS_ROW_DEFAULT = ["설정", "2000-01-01"] # A1, B1 기본값

# --- Helper Function to get records assuming header is on row 2 ---
def get_records_from_row2_header(worksheet, expected_header):
    """
    Fetches all values and constructs records assuming the header is on the 2nd row.
    Row 1 is assumed to be for settings (A1, B1).
    """
    all_values = worksheet.get_all_values()
    
    if len(all_values) < 2: # Not enough rows for settings (row 1) and header (row 2)
        st.warning(f"'{worksheet.title}' 시트에 최소 2개의 행(설정 행, 헤더 행)이 필요하지만, {len(all_values)}행만 존재합니다.")
        return []

    header_row_from_sheet = all_values[1]
    data_rows = all_values[2:]

    # 헤더 유효성 검사 (선택 사항이지만, 디버깅에 유용)
    if list(header_row_from_sheet) != expected_header:
        st.warning(
            f"'{worksheet.title}' 시트의 2번째 행 헤더({header_row_from_sheet})가 예상 헤더({expected_header})와 다릅니다. "
            "데이터는 예상 헤더 기준으로 읽어오려고 시도합니다."
        )
        # 실제 헤더와 예상 헤더의 열 개수가 다를 경우 문제가 될 수 있으므로,
        # 여기서는 예상 헤더의 열 개수만큼만 데이터를 사용하도록 처리할 수 있습니다.
        # 하지만 이 앱에서는 구조가 일치한다고 가정합니다.

    records = []
    for row_values in data_rows:
        # 각 데이터 행의 길이가 헤더 길이보다 짧을 경우 None으로 채움
        padded_row_values = row_values + [None] * (len(expected_header) - len(row_values))
        record = dict(zip(expected_header, padded_row_values))
        records.append(record)
    return records

# --- Helper Function to Ensure Sheet Structure (Row 1 for settings, Row 2 for data header) ---
def ensure_sheet_structure(worksheet, settings_row_content, data_header_content):
    """
    Ensures Row 1 contains settings_row_content (A1, B1) and Row 2 contains data_header_content.
    """
    try:
        all_values = worksheet.get_all_values()

        # Case 1: Sheet is completely empty
        if not all_values:
            worksheet.append_row(settings_row_content, value_input_option='USER_ENTERED') # Appends as Row 1
            worksheet.append_row(data_header_content, value_input_option='USER_ENTERED')  # Appends as Row 2
            st.info(f"'{worksheet.title}' 시트가 비어있어 기본 구조(설정 행 및 데이터 헤더)를 생성했습니다.")
            return

        # Case 2: Sheet has some content, check Row 1 for settings
        current_row1 = all_values[0]
        # A1:B1 범위에 대한 업데이트 (길이가 다를 수 있으므로 특정 셀 지정이 더 안전)
        if len(current_row1) < 1 or current_row1[0] != settings_row_content[0]:
            worksheet.update_cell(1, 1, settings_row_content[0]) # Update A1
            st.info(f"'{worksheet.title}' 시트 A1 셀을 '{settings_row_content[0]}'으로 업데이트했습니다.")
        if len(current_row1) < 2 or not current_row1[1]: # B1이 없거나 비어있으면 초기 날짜로 설정
            worksheet.update_cell(1, 2, settings_row_content[1]) # Update B1
            st.info(f"'{worksheet.title}' 시트 B1 셀을 '{settings_row_content[1]}'으로 업데이트했습니다.")
            
        # Case 3: Check Row 2 for data header
        if len(all_values) < 2: # Row 2 (data header) doesn't exist
            worksheet.append_row(data_header_content, value_input_option='USER_ENTERED') # Appends as Row 2
            st.info(f"'{worksheet.title}' 시트에 2번째 행 데이터 헤더를 추가했습니다.")
        else: # Row 2 exists, check its content
            current_row2 = all_values[1]
            if list(current_row2) != data_header_content:
                st.warning(f"'{worksheet.title}' 시트의 2번째 행 헤더가 예상과 다릅니다. 수정을 시도합니다. 현재: {current_row2}")
                try:
                    header_range = f'A2:{gspread.utils.rowcol_to_a1(2, len(data_header_content))}'
                    worksheet.update(header_range, [data_header_content], value_input_option='USER_ENTERED')
                    st.info(f"'{worksheet.title}' 시트의 2번째 행 헤더를 업데이트했습니다.")
                except Exception as update_e:
                    st.error(f"'{worksheet.title}' 시트 2번째 행 헤더 업데이트 실패: {update_e}")

    except gspread.exceptions.APIError as api_e:
        st.error(f"'{worksheet.title}' 시트 구조 확인/수정 중 Google Sheets API 오류: {api_e}")
    except Exception as e:
        st.error(f"'{worksheet.title}' 시트 구조 확인/수정 중 예기치 않은 오류 발생: {e}")


# --- Google Sheets API 인증 ---
try:
    credentials_dict = st.secrets["GOOGLE_CREDENTIALS"]
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
    client = gspread.authorize(creds)
except Exception as e:
    st.error(f"Google API 인증 중 오류가 발생했습니다: {e}")
    st.stop()

# --- 학생 목록 시트 불러오기 (이 시트는 첫 번째 행을 헤더로 사용한다고 가정) ---
try:
    student_list_ws = client.open("학생목록").sheet1
    students_df = pd.DataFrame(student_list_ws.get_all_records()) 
except gspread.exceptions.SpreadsheetNotFound:
    st.error("학생 목록 시트를 찾을 수 없습니다. Google Sheets에서 '학생목록' 시트가 정확히 있는지, 공유 설정이 올바른지 확인해주세요.")
    st.stop()
except Exception as e: 
    st.error(f"학생 목록을 불러오는 중 오류가 발생했습니다: {e}. '학생목록' 시트의 헤더를 확인해주세요.")
    st.stop()

# --- 세션 상태 초기화 ---
defaults = {
    "logged_in": False, "page": "login", "name": None, "sheet_url": None,
    "emotion": None, "gratitude": "", "message": "", "new_notes": [],
    "new_notes_loaded": False, "b1_updated_this_visit": False,
    "selected_diary_date": None
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
                st.session_state.new_notes_loaded = False
                st.session_state.b1_updated_this_visit = False
                st.session_state.selected_diary_date = None
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
            ensure_sheet_structure(student_ws, SETTINGS_ROW_DEFAULT, EXPECTED_STUDENT_SHEET_HEADER)

            last_checked_date_str = "2000-01-01" # 기본값
            try:
                # B1 셀에서 마지막 확인 날짜 읽기
                b1_val = student_ws.cell(1, 2).value 
                if b1_val: # B1에 값이 있으면 사용
                    last_checked_date_str = b1_val
                # A1셀은 ensure_sheet_structure에서 "설정"으로 관리됨
            except Exception as cell_e: 
                st.warning(f"B1 셀 (마지막 확인 날짜) 읽기 중 오류 발생 (기본값 사용): {cell_e}")
            
            all_diary_entries = get_records_from_row2_header(student_ws, EXPECTED_STUDENT_SHEET_HEADER)
            current_new_notes = []
            
            try:
                last_checked_dt_obj = datetime.strptime(last_checked_date_str, "%Y-%m-%d")
            except ValueError: 
                st.warning(f"저장된 마지막 확인 날짜('{last_checked_date_str}') 형식이 잘못되어 기본값으로 비교합니다.")
                last_checked_dt_obj = datetime.strptime("2000-01-01", "%Y-%m-%d")

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
            st.session_state.new_notes_loaded = True 
        except Exception as e:
            st.error(f"새 쪽지를 확인하는 중 예기치 않은 오류가 발생했습니다: {e}")
            st.session_state.new_notes = [] 
            st.session_state.new_notes_loaded = True
    
    if st.session_state.new_notes:
        st.success(f"읽지 않은 쪽지가 {len(st.session_state.new_notes)}개 있어요!")
        for date_str, note_content in st.session_state.new_notes:
            st.markdown(f"**{date_str}**: {note_content}")
        
        if not st.session_state.b1_updated_this_visit: 
            try:
                latest_note_date_to_save = st.session_state.new_notes[-1][0]
                # student_ws는 이미 위에서 정의됨
                student_ws.update_cell(1, 2, latest_note_date_to_save) # Update B1
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
    
    if st.button("지난 일기 확인/삭제", key="view_past_diary_button"):
        st.session_state.page = "view_modify_diary"
        st.session_state.selected_diary_date = None 
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
    if st.session_state.emotion:
        try:
            group_part, detail_part = st.session_state.emotion.split(" - ", 1)
            if group_part in emotion_dict and detail_part in emotion_dict[group_part]:
                current_emotion_group, current_emotion_detail = group_part, detail_part
        except ValueError: pass 
    
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
                ensure_sheet_structure(student_ws, SETTINGS_ROW_DEFAULT, EXPECTED_STUDENT_SHEET_HEADER)
                
                # 데이터를 읽어올 때는 항상 2번째 행을 헤더로 간주
                records = get_records_from_row2_header(student_ws, EXPECTED_STUDENT_SHEET_HEADER)
                existing_record_idx = -1 # 0-based index for our 'records' list
                note_for_today = "" 

                for idx, record in enumerate(records):
                    if record.get("날짜") == today_date_str:
                        existing_record_idx = idx
                        note_for_today = str(record.get("선생님 쪽지", ""))
                        break
                
                new_entry_data = [
                    today_date_str, st.session_state.emotion,
                    st.session_state.gratitude, st.session_state.message,
                    note_for_today 
                ]

                if existing_record_idx != -1:
                    # 실제 시트에서 업데이트할 행 번호는 existing_record_idx + 3
                    # (1-based + row1 for settings + row2 for header)
                    actual_sheet_row_to_update = existing_record_idx + 3
                    header_range = f'A{actual_sheet_row_to_update}:{gspread.utils.rowcol_to_a1(actual_sheet_row_to_update, len(EXPECTED_STUDENT_SHEET_HEADER))}'
                    student_ws.update(header_range, [new_entry_data], value_input_option='USER_ENTERED')
                    st.success("🔄 오늘의 일기가 성공적으로 수정되었습니다!") 
                else:
                    # append_row는 시트의 마지막 데이터 행 다음에 추가됨 (즉, 헤더 행들 이후)
                    student_ws.append_row(new_entry_data, value_input_option='USER_ENTERED')
                    st.success("🌟 오늘의 일기가 성공적으로 저장되었습니다!") 
                
                st.balloons()
                st.session_state.emotion = None 
                st.session_state.gratitude = ""
                st.session_state.message = ""
                st.session_state.page = "view_modify_diary" 
                st.session_state.selected_diary_date = today_date_str 
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
        ensure_sheet_structure(student_ws, SETTINGS_ROW_DEFAULT, EXPECTED_STUDENT_SHEET_HEADER)
        records = get_records_from_row2_header(student_ws, EXPECTED_STUDENT_SHEET_HEADER)
        
        available_dates = sorted(list(set(r.get("날짜") for r in records if r.get("날짜"))), reverse=True)
        
        default_date_str = st.session_state.get("selected_diary_date")
        if not default_date_str:
            default_date_str = available_dates[0] if available_dates else datetime.today().strftime("%Y-%m-%d")
        elif default_date_str not in available_dates and available_dates:
             default_date_str = available_dates[0]
        elif not available_dates:
             default_date_str = datetime.today().strftime("%Y-%m-%d")

        if not available_dates:
            st.info("작성된 일기가 아직 없습니다.")
            selected_date_str = default_date_str 
        else:
            try:
                default_index = available_dates.index(default_date_str)
            except ValueError: 
                default_index = 0 
            selected_date_str = st.selectbox(
                "확인할 일기 날짜를 선택하세요:", options=available_dates, 
                index=default_index, key="diary_date_selector"
            )
        st.session_state.selected_diary_date = selected_date_str

        found_diary_for_selected_date = False
        diary_to_display = None
        record_idx_to_delete = -1 # 0-based index for 'records' list

        if records: 
            for idx, record in enumerate(records):
                if record.get("날짜") == selected_date_str:
                    diary_to_display = record
                    record_idx_to_delete = idx 
                    found_diary_for_selected_date = True
                    break 

        if found_diary_for_selected_date and diary_to_display:
            st.subheader(f"🗓️ {selected_date_str} 일기") 
            st.write(f"**감정:** {diary_to_display.get('감정', '기록 없음')}")
            st.write(f"**감사한 일:** {diary_to_display.get('감사한 일', '기록 없음')}")
            st.write(f"**하고 싶은 말:** {diary_to_display.get('하고 싶은 말', '기록 없음')}")
            st.write(f"**선생님 쪽지:** {str(diary_to_display.get('선생님 쪽지', '없음'))}") 

            if st.button(f"❌ {selected_date_str} 일기 삭제하기", key="delete_selected_diary_button"): 
                if record_idx_to_delete != -1:
                    # 실제 시트에서 삭제할 행 번호: record_idx_to_delete + 3
                    actual_sheet_row_to_delete = record_idx_to_delete + 3
                    student_ws.delete_rows(actual_sheet_row_to_delete) 
                    st.success(f"✅ {selected_date_str} 일기를 삭제했어요.")
                    st.session_state.selected_diary_date = None 
                    st.rerun() 
                else: 
                    st.error("삭제할 일기를 찾지 못했습니다. 새로고침 후 다시 시도해주세요.")
        elif available_dates : 
             st.info(f"{selected_date_str}에 작성된 일기가 없습니다.")
        
    except gspread.exceptions.APIError as e:
        st.error(f"Google Sheets API 오류로 일기 확인에 실패했습니다: {e}")
    except Exception as e:
        st.error(f"일기를 확인하는 중 오류가 발생했습니다: {e}")

    if st.button("메인 메뉴로 돌아가기", key="view_diary_to_menu"): 
        st.session_state.page = "menu"
        st.session_state.selected_diary_date = None 
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
