import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# 페이지 기본 설정 (Page basic settings)
st.set_page_config(page_title="감정 일기장", page_icon="📘")

# Google Sheets API 인증 (Authentication)
# st.secrets에서 Google Cloud 서비스 계정의 인증 정보를 가져옵니다.
# (Fetches Google Cloud service account credentials from st.secrets.)
try:
    credentials_dict = st.secrets["GOOGLE_CREDENTIALS"]
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
    client = gspread.authorize(creds)
except Exception as e:
    st.error(f"Google API 인증 중 오류가 발생했습니다: {e}")
    st.stop()

# 학생 목록 시트 불러오기 (Load student list sheet)
# "학생목록"이라는 이름의 Google Sheet를 열고 첫 번째 시트를 가져옵니다.
# (Opens the Google Sheet named "학생목록" and gets the first sheet.)
try:
    student_list_ws = client.open("학생목록").sheet1
    students_df = pd.DataFrame(student_list_ws.get_all_records())
except gspread.exceptions.SpreadsheetNotFound:
    st.error("학생 목록 시트를 찾을 수 없습니다. Google Sheets에서 '학생목록' 시트가 정확히 있는지, 공유 설정이 올바른지 확인해주세요.")
    st.stop() # Stop execution if student list is not found
except Exception as e:
    st.error(f"학생 목록을 불러오는 중 오류가 발생했습니다: {e}")
    st.stop()


# 세션 상태 초기화 (Initialize session state)
# 앱의 상태를 저장하기 위한 st.session_state 변수들을 초기화합니다.
# (Initializes st.session_state variables to store the app's state.)
defaults = {
    "logged_in": False,     # 로그인 상태 (Login status)
    "page": 0,              # 현재 페이지 번호 (Current page number)
    "name": None,           # 로그인한 학생 이름 (Logged-in student's name)
    "sheet_url": None,      # 학생 개인 시트 URL (Student's individual sheet URL)
    "emotion": None,        # 선택한 감정 (Selected emotion)
    "gratitude": "",      # 감사한 일 내용 (Gratitude content) - 초기값을 빈 문자열로
    "message": "",        # 하고 싶은 말 내용 (Message content) - 초기값을 빈 문자열로
    "viewing_notes": False, # 쪽지 보기 상태 (Note viewing status)
    "new_notes": []         # 새로운 쪽지 목록 (List of new notes)
}
for key, val in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = val

# ---------------------------
# 페이지 0: 로그인 페이지 (Page 0: Login Page)
# ---------------------------
if st.session_state.page == 0:
    st.title("👧 학생 감정일기 로그인") # Student Emotion Diary Login
    name_input = st.text_input("이름을 입력하세요") # Enter your name
    password_input = st.text_input("비밀번호 (6자리)", type="password", max_chars=6) # Password (6 digits)

    if st.button("다음"): # Next
        name = name_input.strip()
        password = password_input.strip()
        if not name or not password:
            st.warning("이름과 비밀번호를 모두 입력해주세요.") # Please enter both name and password.
        else:
            # 학생 목록에서 이름으로 학생 정보 검색 (Search for student info by name in the student list)
            # 학생 이름이 정확히 일치하는지 확인 (Ensure exact match for student name)
            student_record = students_df[students_df["이름"] == name]
            
            if not student_record.empty and str(student_record.iloc[0]["비밀번호"]).strip() == password:
                # 로그인 성공 (Login successful)
                st.session_state.logged_in = True
                st.session_state.name = name
                st.session_state.sheet_url = student_record.iloc[0]["시트URL"]
                st.session_state.page = 1 # 메뉴 페이지로 이동 (Move to menu page)
                st.rerun() 
            else:
                st.error("이름 또는 비밀번호가 틀린 것 같습니다.") # Name or password seems incorrect.

# ---------------------------
# 페이지 1: 메뉴 페이지 (Page 1: Menu Page)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == 1:
    st.title(f"📘 {st.session_state.name}님의 감정일기 메뉴") # {name}'s Emotion Diary Menu

    # 새 쪽지 확인 로직은 viewing_notes가 False일 때만 실행 (새 쪽지 확인 버튼을 누르기 전)
    if not st.session_state.viewing_notes:
        try:
            student_ws = client.open_by_url(st.session_state.sheet_url).sheet1
            
            # B1 셀에서 마지막 확인 날짜 가져오기, 없으면 초기화
            try:
                last_checked_cell_value = student_ws.cell(1, 2).value # B1 셀
                if not last_checked_cell_value: # B1이 비어있으면
                    student_ws.update_cell(1, 1, "설정") 
                    student_ws.update_cell(1, 2, "2000-01-01")
                    last_checked_date_str = "2000-01-01"
                else:
                    last_checked_date_str = last_checked_cell_value
            except gspread.exceptions.CellNotFound: # B1 셀 자체가 없는 경우 (시트가 매우 작거나 처음 생성)
                student_ws.update_cell(1, 1, "설정") 
                student_ws.update_cell(1, 2, "2000-01-01")
                last_checked_date_str = "2000-01-01"
            except Exception as e: # 기타 gspread 관련 예외
                st.warning(f"마지막 확인 날짜를 가져오는 중 문제 발생 (기본값 사용): {e}")
                last_checked_date_str = "2000-01-01"


            all_diary_entries = student_ws.get_all_records() 
            new_notes_list = []
            
            # 날짜 형식 통일 및 비교를 위한 기준 날짜 객체 생성
            try:
                last_checked_dt_obj = datetime.strptime(last_checked_date_str, "%Y-%m-%d")
            except ValueError:
                st.warning(f"저장된 마지막 확인 날짜('{last_checked_date_str}') 형식이 잘못되어 기본값으로 비교합니다.")
                last_checked_dt_obj = datetime.strptime("2000-01-01", "%Y-%m-%d")


            for record in all_diary_entries:
                entry_date_str = record.get("날짜")
                teacher_note = str(record.get("선생님 쪽지", "")).strip() # 문자열로 변환 후 strip
                if teacher_note and entry_date_str:
                    try:
                        entry_dt_obj = datetime.strptime(entry_date_str, "%Y-%m-%d")
                        if entry_dt_obj > last_checked_dt_obj:
                            new_notes_list.append((entry_date_str, teacher_note))
                    except ValueError:
                        st.warning(f"일기 항목의 날짜('{entry_date_str}') 형식이 올바르지 않아 쪽지를 확인할 수 없습니다.")
                        continue
            
            st.session_state.new_notes = sorted(new_notes_list, key=lambda x: x[0])

        except gspread.exceptions.APIError as e:
            st.error(f"Google Sheets API 오류: {e}. 할당량을 초과했을 수 있습니다. 잠시 후 다시 시도해주세요.")
            st.session_state.new_notes = []
        except Exception as e:
            st.error(f"새로운 쪽지를 확인하는 중 오류가 발생했습니다: {e}")
            st.session_state.new_notes = []

    # 새 쪽지 알림 및 확인 버튼
    if not st.session_state.viewing_notes and st.session_state.new_notes:
        st.success(f"📩 읽지 않은 쪽지가 {len(st.session_state.new_notes)}개 있어요!") 
        if st.button("📖 새 쪽지 확인하기"): 
            st.session_state.viewing_notes = True 
            st.rerun()

    # 쪽지 내용 표시
    if st.session_state.viewing_notes:
        st.subheader("📬 선생님이 보낸 쪽지") 
        if st.session_state.new_notes:
            for date_str, note_content in st.session_state.new_notes:
                st.markdown(f"**{date_str}**: {note_content}")
            
            latest_note_date_to_save = st.session_state.new_notes[-1][0]
            try:
                # 현재 학생 시트를 다시 열어서 작업 (API 호출 최소화를 위해 필요시 조절)
                current_student_ws = client.open_by_url(st.session_state.sheet_url).sheet1
                current_student_ws.update_cell(1, 1, "설정") 
                current_student_ws.update_cell(1, 2, latest_note_date_to_save) 
                st.success("📝 모든 쪽지를 확인했어요.") 
            except Exception as e:
                st.error(f"마지막 확인 날짜 업데이트 중 오류: {e}")
            
            # 쪽지 확인 후 new_notes는 비워주지만, viewing_notes는 메뉴로 돌아가기 전까지 유지
        else:
            st.info("표시할 새 쪽지가 없습니다.")

        if st.button("메뉴로 돌아가기"): 
            st.session_state.viewing_notes = False
            st.session_state.new_notes = [] # 메뉴로 돌아갈 때 쪽지 목록 초기화
            st.rerun()
    else: # viewing_notes가 False일 때만 메뉴 버튼들 표시
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✏️ 오늘 일기 쓰기"): 
                st.session_state.page = 2
                st.rerun()
        with col2:
            if st.button("📖 오늘 일기 확인 및 삭제"): 
                st.session_state.page = "today_diary"
                st.rerun()
        
        if st.button("로그아웃"): 
            for key in defaults.keys(): 
                if key == "page":
                     st.session_state[key] = 0 
                elif key in st.session_state: # 세션에 있는 키만 삭제 또는 기본값으로
                     st.session_state[key] = defaults[key]
            st.rerun()


# ---------------------------
# 페이지 2: 감정 선택 (Page 2: Emotion Selection)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == 2:
    st.title("📘 오늘 감정 선택") 
    emotion_dict = {
        "😀 긍정": ["기쁨", "감사", "자신감", "설렘", "평온"], 
        "😐 보통": ["그냥 그래요", "지루함", "무난함"], 
        "😢 부정": ["슬픔", "불안", "짜증", "화남", "피곤"]  
    }

    # 이전에 선택한 값이 있으면 그걸 기본값으로
    current_emotion_group = None
    current_emotion_detail = None
    if st.session_state.emotion:
        try:
            group_part, detail_part = st.session_state.emotion.split(" - ", 1)
            if group_part in emotion_dict:
                current_emotion_group = group_part
                if detail_part in emotion_dict[group_part]:
                    current_emotion_detail = detail_part
        except ValueError: # " - "가 없는 경우 등
            pass
    
    group_idx = list(emotion_dict.keys()).index(current_emotion_group) if current_emotion_group else 0
    group = st.selectbox("감정 그룹을 선택하세요", list(emotion_dict.keys()), index=group_idx)
    
    detail_idx = emotion_dict[group].index(current_emotion_detail) if current_emotion_detail and current_emotion_group == group else 0
    detail = st.selectbox("구체적인 감정을 선택하세요", emotion_dict[group], index=detail_idx)
    
    st.session_state.emotion = f"{group} - {detail}"

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← 돌아가기"): 
            st.session_state.page = 1
            st.rerun()
    with col_next:
        if st.button("다음 →"): 
            st.session_state.page = 3
            st.rerun()


# ---------------------------
# 페이지 3: 감사한 일 (Page 3: Grateful For)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == 3:
    st.title("📘 감사한 일") 
    st.session_state.gratitude = st.text_area("오늘 감사한 일은 무엇인가요?", height=150, value=st.session_state.gratitude)

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← 돌아가기"): 
            st.session_state.page = 2
            st.rerun()
    with col_next:
        if st.button("다음 →"): 
            st.session_state.page = 4
            st.rerun()

# ---------------------------
# 페이지 4: 하고 싶은 말 (Page 4: Message to Teacher/Friends)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == 4:
    st.title("📘 선생님 또는 친구에게 하고 싶은 말") 
    st.session_state.message = st.text_area("고민이나 친구 이야기 등 무엇이든 적어보세요", height=200, value=st.session_state.message) 

    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← 돌아가기"): 
            st.session_state.page = 3
            st.rerun()
    with col_next:
        if st.button("제출 전 확인 →"): 
            st.session_state.page = 5
            st.rerun()

# ---------------------------
# 페이지 5: 제출 확인 (Page 5: Submission Confirmation)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == 5:
    st.title("✅ 제출 확인") 
    st.write(f"**오늘의 감정:** {st.session_state.emotion}") 
    st.write(f"**감사한 일:** {st.session_state.gratitude}") 
    st.write(f"**하고 싶은 말:** {st.session_state.message}") 

    col_back, col_submit = st.columns(2)
    with col_back:
        if st.button("← 수정하기"): 
            st.session_state.page = 4 
            st.rerun()
    with col_submit:
        if st.button("✔️ 제출하기"): 
            today_date_str = datetime.today().strftime("%Y-%m-%d")
            try:
                student_ws = client.open_by_url(st.session_state.sheet_url).sheet1
                
                header = ["날짜", "감정", "감사한 일", "하고 싶은 말", "선생님 쪽지"]
                # 시트가 비어있거나 헤더가 다르면 헤더 추가/수정
                sheet_values = student_ws.get_all_values()
                if not sheet_values: # 시트가 완전히 비어있는 경우
                    student_ws.append_row(header, value_input_option='USER_ENTERED')
                elif sheet_values[0] != header : # 헤더가 있지만 다른 경우 (첫 행을 헤더로 간주)
                    # 주의: 이 경우 기존 첫 행 데이터가 헤더로 덮어씌워질 수 있음.
                    # 더 안전한 방법은 헤더가 다를 경우 사용자에게 알리거나,
                    # 특정 셀(A1)에 '헤더확인' 같은 값을 넣어두고 관리하는 것.
                    # 여기서는 간단히 첫 행을 업데이트합니다.
                    # student_ws.update('A1', [header]) # 범위로 업데이트해야 함
                    try:
                        student_ws.delete_rows(1) # 기존 첫 행 삭제
                        student_ws.insert_row(header, 1, value_input_option='USER_ENTERED') # 새 헤더 삽입
                    except Exception as header_e:
                         st.warning(f"헤더 업데이트 중 문제 발생: {header_e}. 기존 헤더를 사용할 수 있습니다.")


                records = student_ws.get_all_records() # 헤더 적용 후 레코드 다시 가져오기
                existing_row_index = -1
                note_for_today = "" 

                for idx, record in enumerate(records):
                    if record.get("날짜") == today_date_str:
                        # get_all_records()는 헤더를 제외한 데이터의 리스트를 반환.
                        # 실제 시트 상의 행 번호는 idx + 2 (헤더 행 + 1-based index)
                        existing_row_index = idx + 2  
                        note_for_today = str(record.get("선생님 쪽지", ""))
                        break
                
                new_entry_data = [
                    today_date_str,
                    st.session_state.emotion,
                    st.session_state.gratitude,
                    st.session_state.message,
                    note_for_today 
                ]

                if existing_row_index != -1:
                    # Google Sheets API는 범위로 업데이트해야 함 (예: "A2:E2")
                    student_ws.update(f"A{existing_row_index}:E{existing_row_index}", [new_entry_data], value_input_option='USER_ENTERED')
                    st.success("🔄 오늘의 일기가 성공적으로 수정되었습니다!") 
                else:
                    student_ws.append_row(new_entry_data, value_input_option='USER_ENTERED')
                    st.success("🌟 오늘의 일기가 성공적으로 저장되었습니다!") 
                
                st.balloons()
                # 입력 필드 초기화
                st.session_state.emotion = None # 다음 입력을 위해 None으로
                st.session_state.gratitude = ""
                st.session_state.message = ""
                st.session_state.page = 1 
                st.rerun()

            except gspread.exceptions.APIError as e:
                 st.error(f"Google Sheets API 오류로 저장에 실패했습니다: {e}. 할당량을 초과했거나 권한 문제가 있을 수 있습니다.")
            except Exception as e:
                st.error(f"일기 저장 중 오류가 발생했습니다: {e}")


# ---------------------------
# 페이지 'today_diary': 오늘 일기 확인 및 삭제 (Page 'today_diary': Check/Delete Today's Diary)
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == "today_diary":
    st.title("📖 오늘의 일기 확인 및 삭제") 

    try:
        student_ws = client.open_by_url(st.session_state.sheet_url).sheet1
        # get_all_records()는 헤더가 올바르다고 가정하고 데이터를 가져옴.
        # 헤더가 없는 시트이거나, 헤더가 깨진 경우 문제가 될 수 있음.
        # 다만, 일기 작성 시 헤더를 확인/생성하므로 여기서는 일단 진행.
        records = student_ws.get_all_records() 
        today_date_str = datetime.today().strftime("%Y-%m-%d")
        found_today_diary = False
        diary_to_display = None
        row_to_delete = -1

        for idx, record in enumerate(records):
            if record.get("날짜") == today_date_str:
                diary_to_display = record
                row_to_delete = idx + 2 # 실제 시트 행 번호
                found_today_diary = True
                break 

        if found_today_diary and diary_to_display:
            st.subheader(f"🗓️ {today_date_str} 일기") 
            # .get()의 두 번째 인자는 키가 없을 때 반환할 기본값
            st.write(f"**감정:** {diary_to_display.get('감정', '기록 없음')}")
            st.write(f"**감사한 일:** {diary_to_display.get('감사한 일', '기록 없음')}") # 이 부분을 확인해주세요!
            st.write(f"**하고 싶은 말:** {diary_to_display.get('하고 싶은 말', '기록 없음')}")
            st.write(f"**선생님 쪽지:** {str(diary_to_display.get('선생님 쪽지', '없음'))}") 

            if st.button("❌ 오늘 일기 삭제하기"): 
                if row_to_delete != -1:
                    student_ws.delete_rows(row_to_delete)
                    st.success("✅ 오늘의 일기를 삭제했어요.") 
                    st.session_state.page = 1 
                    st.rerun()
                else: # 이론상 발생하기 어렵지만 방어 코드
                    st.error("삭제할 일기를 찾지 못했습니다.")
        
        if not found_today_diary: # 버튼 표시 전에 이 조건을 먼저 확인
            st.info("오늘 작성된 일기가 없습니다.") 

    except gspread.exceptions.APIError as e:
        st.error(f"Google Sheets API 오류로 일기 확인에 실패했습니다: {e}")
    except Exception as e:
        st.error(f"오늘 일기를 확인하는 중 오류가 발생했습니다: {e}")

    if st.button("← 메뉴로 돌아가기"): 
        st.session_state.page = 1
        st.rerun()

# 로그인되지 않은 경우 또는 알 수 없는 페이지 상태 처리
# (Handle cases where not logged in or unknown page state)
elif not st.session_state.logged_in and st.session_state.page != 0:
    st.session_state.page = 0 
    st.rerun()
