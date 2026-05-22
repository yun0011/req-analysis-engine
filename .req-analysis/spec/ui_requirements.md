# UI 요구사항

> 이 문서는 functional_requirements.json의 ui 섹션을 렌더링한 뷰입니다.
> 정규 소스는 functional_requirements.json이며, 이 문서는 읽기 전용입니다.

---

## 사용자 관리 (DG-USER)

### FR-USER-001 — 로그인할 수 있다

**반환 데이터**

| 필드 | 설명 |
|------|------|
| session_id | 세션 식별자 |
| user | 사용자 정보 |

---

### FR-USER-003 — 사용자 정보를 조회할 수 있다

**표시 필드**

| 필드 | 표시명 |
|------|--------|
| id | 사용자 ID |
| login_id | 아이디 |
| type | 권한 |
| name | 이름 |
| alias | 별명 |
| birth | 생년월일 |
| email | 이메일 |
| phone | 연락처 |
| address | 주소 |
| grade | 배움 과정 |
| status | 학적상태 |
| entrance_date | 입학일자 |
| graduated_date | 졸업일자 |

**상태값 표시 라벨**

| 코드값 | 표시 텍스트 |
|--------|------------|
| grade.H1 | 한배곳 1 |
| grade.H2 | 한배곳 2 |
| grade.H3 | 한배곳 3 |
| grade.H4 | 한배곳 4 |
| grade.D1 | 더배곳 1 |
| grade.D2 | 더배곳 2 |
| grade.DJ | 더배곳 진수 |
| status.ATTENDING | 재학 |
| status.LEAVE | 휴학 |
| status.GRADUATED | 졸업 |
| status.COMPLETED | 수료 |
| status.EXPELLED | 제적 |

---

### FR-USER-004 — 사용자를 등록할 수 있다

**표시 필드** (등록 폼)

| 필드 | 필수 | 표시명 |
|------|------|--------|
| login_id | ✓ | 아이디 |
| type | ✓ | 권한 |
| name.korean | ✓ | 이름 |
| alias | | 별명 |
| birth | ✓ | 생년월일 |
| email | ✓ | 이메일 |
| phone.primary | ✓ | 핸드폰번호 |
| address | ✓ | 집주소 |
| grade | ✓ | 배움 과정 (학생만) |
| status | ✓ | 학적상태 (학생만) |
| entrance_date | ✓ | 입학일자 (학생만) |
| entrance_semester | ✓ | 입학학기 (학생만) |

**상태값 표시 라벨**

| 코드값 | 표시 텍스트 |
|--------|------------|
| grade.H1 | 한배곳 1 |
| grade.H2 | 한배곳 2 |
| grade.H3 | 한배곳 3 |
| grade.H4 | 한배곳 4 |
| grade.D1 | 더배곳 1 |
| grade.D2 | 더배곳 2 |
| grade.DJ | 더배곳 진수 |

---

### FR-USER-005 — 사용자 정보를 수정할 수 있다

**비활성화 조건**

- `loginID` 필드: 항상 비활성화 — 아이디는 등록 후 변경 불가 (UpdateOthers.vue, UpdateStudent.vue)
- `type` 필드: 항상 비활성화 — 비학생 사용자의 권한은 등록 후 변경 불가 (UpdateOthers.vue)

---

## 학기 관리 (DG-TERM)

### FR-TERM-001 — 학기 목록을 조회할 수 있다

**상태값 표시 라벨**

| 코드값 | 표시 텍스트 |
|--------|------------|
| semester.SPRING | 봄 |
| semester.FALL | 가을 |
| status.READY | 준비 중 |
| status.APPLYING | 수강신청 중 |
| status.PROCEEDING | 학기 중 |
| status.FINISHED | 종강 |

---

### FR-TERM-002 — 학기 정보를 수정할 수 있다

**상태값 표시 라벨**

| 코드값 | 표시 텍스트 |
|--------|------------|
| status.READY | 준비 중 |
| status.APPLYING | 수강신청 중 |
| status.PROCEEDING | 학기 중 |
| status.FINISHED | 종강 |

**비활성화 조건**

- 학기 상태가 `FINISHED`이거나 관리자가 아닌 경우 수정/운영 버튼 비활성화 (Operation.vue)

**불가역 작업 확인 가드**

- 학기를 종강 처리할 때 "종강하겠습니다." 텍스트 입력 필요 (Operation.vue)

---

## 배움과정 관리 (DG-COURSE)

### FR-COURSE-001 — 배움과정을 조회할 수 있다

**표시 필드**

| 필드 | 표시명 |
|------|--------|
| id | ID |
| code | 코드 |
| domain | 도메인 |
| name.korean | 국문 명칭 |
| name.english | 영문 명칭 |
| description | 설명 |

---

## 개설수업 관리 (DG-LECTURE)

### FR-LECTURE-001 — 개설수업을 조회할 수 있다

**표시 필드**

| 필드 | 표시명 |
|------|--------|
| id | ID |
| course | 배움과정 |
| user | 담당 교수 |
| category | 수업 유형 |
| enabled | 활성화 여부 |
| graded | 성적처리 완료 여부 |
| term | 학기 |
| registration_status | 수강신청 상태 |
| classroom | 강의실 |
| limit | 정원 |
| approved | 승인 인원 |
| applied | 신청 인원 |
| description | 배움 과정 |
| schedule | 강의 일정 |

**상태값 표시 라벨**

| 코드값 | 표시 텍스트 |
|--------|------------|
| category.ET | 스튜디오/선택 |
| category.RT | 스튜디오/필수 |
| category.EU | 수업/선택 |
| category.RU | 수업/필수 |
| category.EW | 워크숍/선택 |
| category.RW | 워크숍/필수 |
| category.EP | 프로젝트/선택 |
| category.RP | 프로젝트/필수 |
| registration_status.WAITING | 대기 |
| registration_status.APPROVED | 완료 |

---

### FR-LECTURE-002 — 개설수업을 등록할 수 있다

**입력 유효성 검사 메시지**

- "올바른 배움 과정을 입력해주세요." — 배움 과정 버튼이 하나도 선택되지 않은 경우
- "올바른 분류를 입력해주세요." — 수업 유형(category) 미선택 시
- "올바른 강의실을 입력해주세요." — 강의실 미입력 또는 형식 불일치 시
- "올바른 제한인원을 입력해주세요." — 정원 미입력 또는 0 이하 시
- "올바른 일정을 입력해주세요." — 강의 일정 미입력 시

> **참고**: 배움 과정(description 필드)은 UI의 버튼 그룹에서 선택한 과정명을 콤마로 구분한 텍스트로 인코딩되어 전송된다. 예: `"한배곳 1, 한배곳 2"`.

---

### FR-LECTURE-007 — 개설수업을 폐강할 수 있다

**불가역 작업 확인 가드**

- 폐강하기 전 "폐강하겠습니다." 텍스트 입력 필요 (DetailLecture.vue)

---

## 수강신청 관리 (DG-REGISTRATION)

### FR-REGISTRATION-001 — 수강신청 목록을 조회할 수 있다

**표시 필드**

| 필드 | 표시명 |
|------|--------|
| id | ID |
| user | 수강자 |
| lecture | 개설수업 |
| status | 신청 상태 |
| attendance | 출석률 |
| evaluated | 평가 완료 여부 |
| passed | 통과여부 |
| recommended | 추천여부 |
| comment | 평가 의견 |

**상태값 표시 라벨**

| 코드값 | 표시 텍스트 |
|--------|------------|
| status.WAITING | 대기 |
| status.APPROVED | 완료 |
| passed.true | P |
| passed.false | F |
| passed.null | P/F |

---

### FR-REGISTRATION-003 — 학생이 봄학기 수강신청을 할 수 있다

**비동기 폴링**

- 봄학기 수강신청 후 처리 결과 확인을 위해 3000ms 간격으로 `/api/v1/request/get/status` 반복 호출
- 종료 조건: 상태가 `PENDING`이 아닐 때 (WAITING 또는 APPROVED로 변경)

---

### FR-REGISTRATION-007 — 수강생 성적을 입력할 수 있다

**입력 유효성 검사 메시지**

- "올바른 통과여부를 선택해 주세요." — passed 미선택 시
- "올바른 평가를 선택해 주세요." — recommended 미선택 시

**표시 필드**

| 필드 | 필수 | 표시명 |
|------|------|--------|
| passed | ✓ | 통과여부 |
| recommended | ✓ | 추천여부 |
| comment | ✓ | 평가 의견 (1~300자) |

**상태값 표시 라벨**

| 코드값 | 표시 텍스트 |
|--------|------------|
| passed.true | P |
| passed.false | F |
| passed.null | P/F |

---

## 공지사항 (DG-NOTICE)

### FR-NOTICE-001 — 공지사항을 조회할 수 있다

**표시 필드**

| 필드 | 표시명 |
|------|--------|
| id | ID |
| type | 유형 |
| title | 제목 |
| content | 내용 |
| attachment | 첨부파일 |
| timestamp | 등록일시 |

---

## 규정 (DG-RULE)

### FR-RULE-001 — 규정을 조회할 수 있다

**표시 필드**

| 필드 | 표시명 |
|------|--------|
| id | ID |
| type | 유형 |
| title | 제목 |
| content | 내용 |
| attachment | 첨부파일 |
| timestamp | 등록일시 |

---

## 학사일정 (DG-SCHEDULE)

### FR-SCHEDULE-001 — 학사일정을 조회할 수 있다

**표시 필드**

| 필드 | 표시명 |
|------|--------|
| id | ID |
| type | 유형 |
| title | 제목 |
| content | 내용 |
| timestamp | 등록일시 |

---

## 출석 관리 (DG-ATTENDANCE)

### FR-ATTENDANCE-001 — 출석 목록을 조회할 수 있다

**상태값 표시 라벨**

| 코드값 | 표시 텍스트 |
|--------|------------|
| status.ATTEND | 출석 |
| status.TARDY | 지각 |
| status.HALF_TARDY | 반지각 |
| status.ABSENCE | 결석 |
| status.EXCUSED_ABSENCE | 공결 |
| status.EARLY_LEAVE | 조퇴 |

---

### FR-ATTENDANCE-002 — 출석 상태를 입력할 수 있다

**상태값 표시 라벨**

| 코드값 | 표시 텍스트 |
|--------|------------|
| status.ATTEND | 출석 |
| status.TARDY | 지각 |
| status.HALF_TARDY | 반지각 |
| status.ABSENCE | 결석 |
| status.EXCUSED_ABSENCE | 공결 |
| status.EARLY_LEAVE | 조퇴 |

---

## 강의평가 (DG-EVALUATION)

### FR-EVALUATION-001 — 강의평가를 조회할 수 있다

**표시 필드**

| 필드 | 표시명 |
|------|--------|
| id | ID |
| user | 평가자 |
| lecture | 개설수업 |
| satisfaction | 만족도 |
| achievement | 성취도 |
| positive | 좋은 점 |
| negative | 아쉬운 점 |
| comment | 기타 의견 |

---

## 수료증 (DG-CERTIFICATE)

### FR-CERTIFICATE-001 — 수료증을 조회할 수 있다

**표시 필드**

| 필드 | 표시명 |
|------|--------|
| id | ID |
| user | 수료자 |
| lecture | 수료 과목 |
| issued_at | 발급일시 |

---

## 파일 저장소 (DG-DRIVE)

### FR-DRIVE-001 — 파일 목록을 조회하고 다운로드할 수 있다

**표시 필드**

| 필드 | 표시명 |
|------|--------|
| id | 파일 ID |
| name | 파일명 |
| type | 파일 유형 |
| size | 크기 |

---

## 횡단 UI 제약

- **XC-AUTH-001**: 세션이 없는 사용자는 로그인 화면으로 리디렉션되어야 한다 (route_guard)
- **XC-PERM-001**: 역할에 맞지 않는 메뉴/기능은 화면에서 숨기거나 비활성화해야 한다
- **XC-PAGINATION-001**: 목록 화면에서 첫 번째 페이지에서 이전 버튼 클릭 시 "첫번째 페이지입니다." 메시지를 표시해야 한다 (공통 페이지네이션 컴포넌트)
- **XC-STATUS-001**: 오류 응답 시 도메인 상태코드에 대응하는 사용자 친화적 메시지를 표시해야 한다
