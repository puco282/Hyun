import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

st.set_page_config(page_title="감정 일기장", page_icon="📘")

# 구글 인증
credentials_dict = st.secrets["GOOGLE_CREDENTIALS"]
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
client = gspread.authorize(creds)

# 학생 목록 불러오기
student_list_ws = client.open("학생목록").sheet1
students_df = pd.DataFrame(student_list_ws.get_all_records())

# 세션 상태 초기화
for key in ["logged_in", "page", "name", "sheet_url", "emotion", "gratitude", "message"]:
    if key not in st.session_state:
        st.session_state[key] = 0 if key == "page" else None

# ---------------------------
# 로그인
# ---------------------------
if st.session_state.page == 0:
    st.title("👧 학생 감정일기 로그인")
    name = st.text_input("이름을 입력하세요")
    password = st.text_input("비밀번호 (6자리)", type="password", max_chars=6)

    if st.button("다음"):
        if name.strip() == "" or password.strip() == "":
            st.warning("이름과 비밀번호를 모두 입력해주세요.")
        else:
            row = students_df[students_df["이름"] == name.strip()]
            if not row.empty and str(row.iloc[0]["비밀번호"]).strip() == password.strip():
                st.session_state.logged_in = True
                st.session_state.name = name
                st.session_state.sheet_url = row.iloc[0]["시트URL"]
                st.session_state.page = 1
                st.experimental_rerun()
            else:
                st.error("이름 또는 비밀번호가 틀린 것 같습니다.")

# ---------------------------
# 메뉴 페이지
# ---------------------------
elif st.session_state.logged_in and st.session_state.page == 1:
    st.title(f"📘 {st.session_state.name}님의 감정일기 메뉴")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("✏️ 오늘 일기 쓰기"):
            st.session_state.page = 2
            st.experimental_rerun()
    with col2:
        if st.button("📖 오늘 일기 확인 및 삭제"):
            st.session_state.page = "today_diary"
            st.experimental_rerun()

# ---------------------------
# 감정 선택
# ---------------------------
elif st.session_state.page == 2:
    st.title("📘 오늘 감정 선택")
    emotion_dict = {
        "😀 긍정": ["기쁨", "감사", "자신감", "설렘", "평온"],
        "😐 보통": ["그냥 그래요", "지루함", "무난함"],
        "😢 부정": ["슬픔", "불안", "짜증", "화남", "피곤"]
    }

    group = st.selectbox("감정 그룹을 선택하세요", list(emotion_dict.keys()))
    detail = st.selectbox("구체적인 감정을 선택하세요", emotion_dict[group])
    st.session_state.emotion = f"{group} - {detail}"

    if st.button("다음 →"):
        st.session_state.page = 3
        st.experimental_rerun()

    if st.button("← 돌아가기"):
        st.session_state.page = 1
        st.experimental_rerun()

# ---------------------------
# 감사한 일
# ---------------------------
elif st.session_state.page == 3:
    st.title("📘 감사한 일")
    st.session_state.gratitude = st.text_area("오늘 감사한 일은 무엇인가요?")

    if st.button("다음 →"):
        st.session_state.page = 4
        st.experimental_rerun()

    if st.button("← 돌아가기"):
        st.session_state.page = 2
        st.experimental_rerun()

# ---------------------------
# 하고 싶은 말
# ---------------------------
elif st.session_state.page == 4:
    st.title("📘 선생님 또는 친구에게 하고 싶은 말")
    st.session_state.message = st.text_area("고민이나 친구 이야기 등 무엇이든 적어보세요")

    if st.button("제출 전 확인 →"):
        st.session_state.page = 5
        st.experimental_rerun()

    if st.button("← 돌아가기"):
        st.session_state.page = 3
        st.experimental_rerun()

# ---------------------------
# 제출 확인
# ---------------------------
elif st.session_state.page == 5:
    st.title("✅ 제출 확인")
    st.write(f"**오늘의 감정:** {st.session_state.emotion}")
    st.write(f"**감사한 일:** {st.session_state.gratitude}")
    st.write(f"**하고 싶은 말:** {st.session_state.message}")

    if st.button("제출하기"):
        today = datetime.today().strftime("%Y-%m-%d")
        student_ws = client.open_by_url(st.session_state.sheet_url).sheet1

        # 선생님 쪽지 자동 불러오기
        try:
            data = student_ws.get_all_records()
            note_for_today = ""
            for row in data:
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

        st.success("🌟 오늘의 일기가 성공적으로 저장되었습니다!")
        st.balloons()
        st.session_state.page = 1
        st.experimental_rerun()

    if st.button("← 돌아가기"):
        st.session_state.page = 4
        st.experimental_rerun()

# ---------------------------
# 오늘 일기 확인 및 삭제
# ---------------------------
elif st.session_state.page == "today_diary":
    st.title("📖 오늘의 일기 확인 및 삭제")

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
                    student_ws.delete_rows(idx + 2)
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
