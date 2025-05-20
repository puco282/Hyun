import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# 페이지 기본 설정 (Page basic settings)
st.set_page_config(page_title="감정 일기장", page_icon="📘")

# --- Helper Function to Ensure Correct Sheet Header ---
def ensure_sheet_header(worksheet, expected_header):
    """
    Ensures the worksheet has the correct header row.
    If the sheet is empty or the header is incorrect, it sets the correct header.
    Raises a ValueError if it fails to ensure the header.
    """
    try:
        sheet_values = worksheet.get_all_values() 

        if not sheet_values:
            worksheet.append_row(expected_header, value_input_option='USER_ENTERED')
            st.info(f"'{worksheet.title}' 시트가 비어있어 헤더를 새로 생성했습니다.")
        elif sheet_values[0] != expected_header:
            try:
                worksheet.delete_rows(1) 
                worksheet.insert_row(expected_header, 1, value_input_option='USER_ENTERED')
                st.warning(f"'{worksheet.title}' 시트의 헤더를 올바른 형식으로 수정했습니다.")
            except Exception as e:
                # delete_rows나 insert_row 실패 시 worksheet.clear() 후 헤더 추가 시도
                st.warning(f"'{worksheet.title}' 시트 헤더 직접 수정 실패 (오류: {e}). 시트를 초기화하고 헤더를 다시 설정합니다.")
                try:
                    worksheet.clear()
                    worksheet.append_row(expected_header, value_input_option='USER_ENTERED')
                    st.info(f"'{worksheet.title}' 시트를 초기화하고 헤더를 새로 생성했습니다.")
                except Exception as clear_e:
                    st.error(f"'{worksheet.title}' 시트 초기화 및 헤더 생성 중 심각한 오류 발생: {clear_e}")
                    raise ValueError(f"시트 헤더를 설정하는 데 최종적으로 실패했습니다: {clear_e}")
        
    except gspread.exceptions.APIError as api_e:
        st.error(f"'{worksheet.title}' 시트 접근 중 Google Sheets API 오류: {api_e}")
        raise ValueError(f"시트 헤더 확인 중 API 오류: {api_e}")
    except Exception as e:
        st.error(f"'{worksheet.title}' 시트 헤더 확인 중 예기치 않은 오류 발생: {e}")
        raise ValueError(f"시트 헤더 확인 중 예기치 않은 오류: {e}")

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
    students_df = pd.DataFrame(student_list_ws.get_all_records())
except gspread.exceptions.SpreadsheetNotFound:
    st.error("학생 목록 시트를 찾을 수 없습니다. Google Sheets에서 '학생목록' 시트가 정확히 있는지, 공유 설정이 올바른지 확인해주세요.")
    st.stop()
except Exception as e:
    st.error(f"학생 목록을 불러오는 중 오류가 발생했습니다: {e}")
    st.stop()

# --- 세션 상태 초기화 ---
defaults = {
    "logged_in": False, "page": "login", "name": None, "sheet_url": None,
    "emotion": None, "gratitude": "", "message": "", "new_notes": []
    # viewing_notes는 이제 check_notes 페이지 자체로 대체됨
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- 학생 시트 예상 헤더 ---
EXPECTED_STUDENT_SHEET_HEADER = ["날짜", "감정", "감사한 일", "하고 싶은 말", "선생님 쪽지"]

# ---------------------------
# 페이지: 로그인 (Page: Login)
# ---------------------------
if st.session_state.page == "login":
    st.title("👧 학생 감정일기 로그인")
    name_input = st.text_input("이름을 입력하세요")
    password_input = st.text_input("비밀번호 (6자리)", type="password", max_chars=6)

    if st.button("로그인"):
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
                st.session_state.page = "check_notes" # 로그인 후 새 쪽지 확인 페이지로
                st.rerun() 
            else:
                st.error("이름 또는 비밀번호가 틀린 것 같습니다.")

# ---------------------------
# 페이지: 새로운 쪽지 확인 (Page: Check New Notes)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == "check_notes":
    st.title(f"📬 {st.session_state.name}님, 새로운 쪽지를 확인하세요")
    new_notes_processed_this_run = False # 중복 처리를 막기 위한 플래그

    if not st.session_state.get("new_notes_loaded", False): # 최초 한번만 쪽지 로드
        try:
            student_ws = client.open_by_url(st.session_state.sheet_url).sheet1
            ensure_sheet_header(student_ws, EXPECTED_STUDENT_SHEET_HEADER)

            last_checked_date_str = "2000-01-01" # 기본값
            try:
                cell_val = student_ws.cell(1, 2).value # B1 셀 확인
                if cell_val:
                    last_checked_date_str = cell_val
                else: # B1이 비어있으면 초기화
                    student_ws.update_cell(1, 1, "설정")
                    student_ws.update_cell(1, 2, "2000-01-01")
            except gspread.exceptions.CellNotFound: # B1 셀 자체가 없는 경우
                student_ws.update_cell(1, 1, "설정")
                student_ws.update_cell(1, 2, "2000-01-01")
            
            all_diary_entries = student_ws.get_all_records()
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
            st.session_state.new_notes_loaded = True # 로드 완료 플래그

        except ValueError as ve:
             st.error(f"학생 시트 처리 중 오류: {ve}")
             st.session_state.new_notes = []
        except gspread.exceptions.APIError as e:
            st.error(f"새 쪽지 확인 중 Google Sheets API 오류: {e}")
            st.session_state.new_notes = []
        except Exception as e:
            st.error(f"새 쪽지를 확인하는 중 예기치 않은 오류가 발생했습니다: {e}")
            st.session_state.new_notes = []
    
    # 쪽지 표시
    if st.session_state.new_notes:
        st.success(f"읽지 않은 쪽지가 {len(st.session_state.new_notes)}개 있어요!")
        for date_str, note_content in st.session_state.new_notes:
            st.markdown(f"**{date_str}**: {note_content}")
        
        # 마지막 확인 날짜 업데이트 (쪽지를 모두 보여준 후에)
        if not new_notes_processed_this_run:
            try:
                latest_note_date_to_save = st.session_state.new_notes[-1][0]
                student_ws_for_update = client.open_by_url(st.session_state.sheet_url).sheet1 # 시트 다시 열기
                student_ws_for_update.update_cell(1, 2, latest_note_date_to_save)
                st.info("모든 새 쪽지를 확인했습니다. 마지막 확인 날짜가 업데이트되었습니다.")
                st.session_state.new_notes = [] # 확인 후 비우기 (다음 rerun 시 다시 로드되지 않도록)
                new_notes_processed_this_run = True
            except Exception as e:
                st.error(f"마지막 확인 날짜 업데이트 중 오류: {e}")
    else:
        st.info("새로운 쪽지가 없습니다.")

    if st.button("메인 메뉴로 가기"):
        st.session_state.page = "menu"
        st.session_state.new_notes_loaded = False # 다음 로그인 시 쪽지 다시 로드하도록
        st.session_state.new_notes = [] # 명시적으로 비워줌
        st.rerun()
    
    if st.button("로그아웃", key="logout_check_notes"):
        for key_to_reset in defaults.keys(): st.session_state[key_to_reset] = defaults[key_to_reset]
        st.session_state.new_notes_loaded = False
        st.rerun()

# ---------------------------
# 페이지: 메인 메뉴 (Page: Main Menu)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == "menu":
    st.title(f"📘 {st.session_state.name}님의 감정일기 메뉴")
    
    if st.button("✏️ 오늘 일기 쓰기"):
        st.session_state.page = "write_emotion"
        st.rerun()
    
    # "오늘 일기 확인 및 삭제" 버튼은 일기 제출 후 페이지로 이동하므로 메뉴에서는 제거
    # 필요하다면 여기에 "지난 일기 보기" 같은 다른 기능을 추가할 수 있습니다.

    if st.button("로그아웃", key="logout_menu"):
        for key_to_reset in defaults.keys(): st.session_state[key_to_reset] = defaults[key_to_reset]
        st.session_state.new_notes_loaded = False # 로그아웃 시 쪽지 로드 플래그 초기화
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
    group = st.selectbox("감정 그룹", list(emotion_dict.keys()), index=group_idx)
    
    detail_idx = emotion_dict[group].index(current_emotion_detail) if current_emotion_detail and current_emotion_group == group else 0
    detail = st.selectbox("구체적인 감정", emotion_dict[group], index=detail_idx)
    st.session_state.emotion = f"{group} - {detail}"

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← 메인 메뉴"): 
            st.session_state.page = "menu"
            st.rerun()
    with col_next:
        if st.button("다음: 감사한 일 →"): 
            st.session_state.page = "write_gratitude"
            st.rerun()

# ---------------------------
# 페이지: 감사한 일 (Page: Write Diary - Gratitude)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == "write_gratitude":
    st.title("오늘 감사했던 일을 적어보세요")
    st.session_state.gratitude = st.text_area("감사한 일", height=150, value=st.session_state.gratitude)

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← 이전: 감정 선택"): 
            st.session_state.page = "write_emotion"
            st.rerun()
    with col_next:
        if st.button("다음: 하고 싶은 말 →"): 
            st.session_state.page = "write_message"
            st.rerun()

# ---------------------------
# 페이지: 하고 싶은 말 (Page: Write Diary - Message)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == "write_message":
    st.title("선생님이나 친구에게 하고 싶은 말이 있나요?")
    st.session_state.message = st.text_area("하고 싶은 말", height=200, value=st.session_state.message) 

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← 이전: 감사한 일"): 
            st.session_state.page = "write_gratitude"
            st.rerun()
    with col_next:
        if st.button("다음: 제출 전 확인 →"): 
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
        if st.button("← 이전: 수정하기"): 
            st.session_state.page = "write_message" 
            st.rerun()
    with col_submit:
        if st.button("✔️ 제출하기"): 
            today_date_str = datetime.today().strftime("%Y-%m-%d")
            try:
                student_ws = client.open_by_url(st.session_state.sheet_url).sheet1
                ensure_sheet_header(student_ws, EXPECTED_STUDENT_SHEET_HEADER)
                
                records = student_ws.get_all_records() 
                existing_row_index = -1
                note_for_today = "" 

                for idx, record in enumerate(records):
                    if record.get("날짜") == today_date_str:
                        existing_row_index = idx + 2  
                        note_for_today = str(record.get("선생님 쪽지", ""))
                        break
                
                new_entry_data = [
                    today_date_str, st.session_state.emotion,
                    st.session_state.gratitude, st.session_state.message,
                    note_for_today 
                ]

                if existing_row_index != -1:
                    student_ws.update(f"A{existing_row_index}:E{existing_row_index}", [new_entry_data], value_input_option='USER_ENTERED')
                    st.success("🔄 오늘의 일기가 성공적으로 수정되었습니다!") 
                else:
                    student_ws.append_row(new_entry_data, value_input_option='USER_ENTERED')
                    st.success("🌟 오늘의 일기가 성공적으로 저장되었습니다!") 
                
                st.balloons()
                # 입력 필드 초기화
                st.session_state.emotion = None 
                st.session_state.gratitude = ""
                st.session_state.message = ""
                st.session_state.page = "view_today_diary" # 제출 후 오늘 일기 확인 페이지로
                st.rerun()

            except ValueError as ve: 
                 st.error(f"일기 저장 중 시트 처리 오류: {ve}")
            except gspread.exceptions.APIError as e:
                 st.error(f"Google Sheets API 오류로 저장에 실패했습니다: {e}")
            except Exception as e:
                st.error(f"일기 저장 중 오류가 발생했습니다: {e}")

# ---------------------------
# 페이지: 오늘 일기 확인 및 삭제 (Page: View/Delete Today's Diary - after submission)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == "view_today_diary":
    st.title("📖 오늘 작성한 일기") 

    try:
        student_ws = client.open_by_url(st.session_state.sheet_url).sheet1
        ensure_sheet_header(student_ws, EXPECTED_STUDENT_SHEET_HEADER)

        records = student_ws.get_all_records() 
        today_date_str = datetime.today().strftime("%Y-%m-%d")
        found_today_diary = False
        diary_to_display = None
        row_to_delete = -1

        for idx, record in enumerate(records):
            if record.get("날짜") == today_date_str:
                diary_to_display = record
                row_to_delete = idx + 2 
                found_today_diary = True
                break 

        if found_today_diary and diary_to_display:
            st.subheader(f"🗓️ {today_date_str} 일기") 
            st.write(f"**감정:** {diary_to_display.get('감정', '기록 없음')}")
            st.write(f"**감사한 일:** {diary_to_display.get('감사한 일', '기록 없음')}")
            st.write(f"**하고 싶은 말:** {diary_to_display.get('하고 싶은 말', '기록 없음')}")
            st.write(f"**선생님 쪽지:** {str(diary_to_display.get('선생님 쪽지', '없음'))}") 

            if st.button("❌ 이 일기 삭제하기"): 
                if row_to_delete != -1:
                    student_ws.delete_rows(row_to_delete)
                    st.success("✅ 오늘의 일기를 삭제했어요.") 
                    # 삭제 후에는 메인 메뉴로 이동
                    st.session_state.page = "menu" 
                    st.rerun()
                else: 
                    st.error("삭제할 일기를 찾지 못했습니다. 새로고침 후 다시 시도해주세요.")
        elif not found_today_diary: # 오늘 일기가 없는 경우 (예: 방금 삭제한 경우)
             st.info("오늘 작성된 일기가 없습니다. 새로 작성하시겠어요?")


    except ValueError as ve: 
        st.error(f"오늘 일기 확인 중 시트 처리 오류: {ve}")
    except gspread.exceptions.APIError as e:
        st.error(f"Google Sheets API 오류로 일기 확인에 실패했습니다: {e}")
    except Exception as e:
        st.error(f"오늘 일기를 확인하는 중 오류가 발생했습니다: {e}")

    if st.button("메인 메뉴로 돌아가기"): 
        st.session_state.page = "menu"
        st.rerun()
    
    if st.button("로그아웃", key="logout_view_diary"):
        for key_to_reset in defaults.keys(): st.session_state[key_to_reset] = defaults[key_to_reset]
        st.session_state.new_notes_loaded = False
        st.rerun()

# --- 로그인되지 않은 경우 또는 알 수 없는 페이지 상태 처리 ---
elif not st.session_state.logged_in and st.session_state.page != "login":
    # 모든 세션 상태를 기본값으로 초기화하고 로그인 페이지로 강제 이동
    for key_to_reset in defaults.keys(): 
        st.session_state[key_to_reset] = defaults[key_to_reset]
    st.session_state.page = "login" 
    st.rerun()
