import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

st.set_page_config(page_title="감정 일기장", page_icon="📘")

# ✅ Streamlit Cloud가 secrets객 GOOGLE_CREDENTIALS 이용
credentials_dict = st.secrets["GOOGLE_CREDENTIALS"]

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
client = gspread.authorize(creds)

# 학생 목록 및 통합 기록 시트 로드
student_list_ws = client.open("학생목록").sheet1
teacher_log_ss = client.open("통합기록")
students_df = pd.DataFrame(student_list_ws.get_all_records())

# 상태 초기화
for key in ["logged_in", "page", "name", "sheet_url", "emotion", "gratitude", "message", "diary_offset"]:
    if key not in st.session_state:
        st.session_state[key] = 0 if key == "page" else None

# 로그인 페이지
if st.session_state.page == 0:
    st.title("👧 학생 감정일기 로그인")
    name = st.selectbox("이름을 선택하세요", students_df["이름"])
    password = st.text_input("비밀번호 (6자리)", type="password", max_chars=6)

    col1, col2 = st.columns([1, 1])
    with col2:
        if st.button("다음"):
            row = students_df[students_df["이름"] == name]
            db_password = str(row.iloc[0]["비밀번호"]).strip()
            input_password = password.strip()
            if not row.empty and db_password == input_password:
                st.session_state.logged_in = True
                st.session_state.name = name
                st.session_state.sheet_url = row.iloc[0]["시트URL"]
                st.session_state.page = 1
            else:
                st.error("이름 또는 비밀번호가 틀린 것 같습니다.")

# 메뉴 페이지 (1)
elif st.session_state.logged_in and st.session_state.page == 1:
    st.title(f"📘 {st.session_state.name}님의 감정일기 메뉴")

    # 📨 새 쪽지 확인
    try:
        student_ws = client.open_by_url(st.session_state.sheet_url).sheet1
        last_checked = student_ws.cell(1, 2).value or "2000-01-01"
    except:
        last_checked = "2000-01-01"

    new_notes = []
    try:
        teacher_note_ws = teacher_log_ss.worksheet(st.session_state.name)
        notes_data = teacher_note_ws.get_all_records()
        for row in notes_data:
            note_date = row.get("날짜")
            note_content = row.get("선생님 쪽지", "").strip()
            if note_date > last_checked and note_content:
                new_notes.append((note_date, note_content))
    except:
        new_notes = []

    if new_notes:
        st.success(f"📩 읽지 않은 새 쪽지가 {len(new_notes)}개 있어요!")
        if st.button("📖 새 쪽지 확인하기"):
            for d, c in new_notes:
                st.markdown(f"**{d}**: {c}")
            # 가장 마지막 쪽지 날짜를 기록
            latest_date = new_notes[-1][0]
            student_ws.update_cell(1, 2, latest_date)
            st.success("📝 모든 쪽지를 확인했어요.")
            st.experimental_rerun()
    else:
        st.info("읽지 않은 쪽지가 없어요.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✏️ 오늘 일기 쓰기"):
            st.session_state.page = 2
    with col2:
        if st.button("📖 오늘 일기 확인 및 삭제"):
    st.session_state.page = "today_diary"
    st.experimental_rerun()

# 감정 선택 (2)
elif st.session_state.page == 2:

    st.title("📘 오늘 감정 선택")

    emotion_dict = {
        "😀 긍정": ["기쁨", "감사", "자신감", "설렘", "평온"],
        "😐 보통": ["그냥 그래요", "지루함", "무난함"],
        "😢 부정": ["슬픔", "불안", "짜증", "화남", "피곤"]
    }

    emotion_group = st.selectbox("감정 그룹을 선택하세요", list(emotion_dict.keys()))
    emotion_detail = st.selectbox("구체적인 감정을 선택하세요", emotion_dict[emotion_group])
    st.session_state.emotion = f"{emotion_group} - {emotion_detail}"

    if st.button("다음 →"):
        st.session_state.page = 3
        st.experimental_rerun()


# 감사 일 (3)
elif st.session_state.page == 3:
    st.title("📘 감사한 일")

    if st.button("← 돌아가기"):
        st.session_state.page = 1
        st.experimental_rerun()
    st.session_state.gratitude = st.text_area("오늘 감사한 일은 무엇인가요?")
    if st.button("다음 →", key="next2"):
        st.session_state.page = 4

# 하고 싶은 말 (4)
elif st.session_state.page == 4:
    st.title("📘 학교에게 하고 싶은 말")

    if st.button("← 돌아가기"):
        st.session_state.page = 1
        st.experimental_rerun()
    st.session_state.message = st.text_area("고민이나 친구 이야기 등 무엇이든 적어보세요")
    if st.button("제출 전 확인 →"):
        st.session_state.page = 5

# 제출 확인 (5)
elif st.session_state.page == 5:
    st.title("✅ 제출 확인")

    if st.button("← 돌아가기"):
        st.session_state.page = 1
        st.experimental_rerun()
    st.write(f"**이름:** {st.session_state.name}")
    st.write(f"**오늘의 감정:** {st.session_state.emotion}")
    st.write(f"**감사한 일:** {st.session_state.gratitude}")
    st.write(f"**하고 싶은 말:** {st.session_state.message}")

    if st.button("제출하기"):
        today = datetime.today().strftime("%Y-%m-%d")
        student_ws = client.open_by_url(st.session_state.sheet_url).sheet1

        # 선생말 보기
        try:
            teacher_note_ws = teacher_log_ss.worksheet(st.session_state.name)
            notes_data = teacher_note_ws.get_all_records()
            note_for_today = ""
            for row in notes_data:
                if row.get("날짜") == today:
                    note_for_today = row.get("선생님 쪽지", "")
                    break
        except:
            note_for_today = ""

        student_ws.append_row([
            today,
            st.session_state.emotion,
            st.session_state.gratitude,
            st.session_state.message,
            note_for_today
        ])

        try:
            teacher_ws = teacher_log_ss.worksheet(st.session_state.name)
        except gspread.WorksheetNotFound:
            teacher_ws = teacher_log_ss.add_worksheet(title=st.session_state.name, rows="100", cols="6")
            teacher_ws.append_row(["날짜", "감정", "감사한 일", "하고 싶은 말", "선생님 쪽지", "비고"])

        teacher_ws.append_row([
            today,
            st.session_state.emotion,
            st.session_state.gratitude,
            st.session_state.message,
            note_for_today,
            ""
        ])

        st.success("🌟 오늘의 일기가 성공적으로 저장되었습니다!")
        st.balloons()
        st.session_state.page = 1
        st.session_state.diary_offset = 0

# 일기 보기 페이지
    try:
        student_ws = client.open_by_url(st.session_state.sheet_url).sheet1
        data = student_ws.get_all_records()
        if data:
            df = pd.DataFrame(data)
            total_rows = len(df)
            offset = st.session_state.diary_offset or 0
            visible_count = 5 + offset
            st.dataframe(df.tail(visible_count).reset_index(drop=True))

            if visible_count < total_rows:
                if st.button("⬅️ 이전 기록 더 보기"):
                    st.session_state.diary_offset += 5
            else:
                st.info("모든 기록을 다 불러왔어요!")
        else:
            st.info("아직 작성된 일기가 없습니다.")

    except Exception as e:
        st.error(f"오류: {e}")

    if st.button("← 돌아가기"):
        st.session_state.page = 1
        st.session_state.diary_offset = 0

elif st.session_state.page == "today_diary":
    st.title(f"📖 오늘의 일기 확인 및 삭제")

    try:
        student_ws = client.open_by_url(st.session_state.sheet_url).sheet1
        records = student_ws.get_all_records()
        today = datetime.today().strftime("%Y-%m-%d")
        found = False

        for idx, row in enumerate(records):
            if row.get("날짜") == today:
                st.write(f"**감정:** {row.get('감정', '')}")
                st.write(f"**감사한 일:** {row.get('감사한 일', '')}")
                st.write(f"**하고 싶은 말:** {row.get('하고 싶은 말', '')}")
                st.write(f"**선생님 쪽지:** {row.get('선생님 쪽지', '')}")
                found = True

                if st.button("❌ 오늘 일기 삭제하기"):
                    student_ws.delete_rows(idx + 2)  # account for header row
                    st.success("✅ 오늘의 일기를 삭제했어요.")
                    st.experimental_rerun()
                break

        if not found:
            st.info("오늘 작성된 일기가 없습니다.")

    except Exception as e:
        st.error(f"오류 발생: {e}")

    if st.button("← 돌아가기"):
        st.session_state.page = 1
        st.experimental_rerun()
