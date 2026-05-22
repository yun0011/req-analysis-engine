# UI 요구사항

> 이 문서는 functional_requirements.json의 ui 섹션을 렌더링한 뷰입니다.
> 정규 소스는 functional_requirements.json이며, 이 문서는 읽기 전용입니다.
> 생성일: 2026-05-22

---

## 사용자 관리 (DG-USER)

### FR-USER-003 — 새 사용자를 등록할 수 있다

**표시 필드**: id, login_id, type, korean_name, english_name, grade, status

**상태값 표시 라벨**

| 필드 | 코드값 | 표시 텍스트 |
|------|--------|------------|
| grade | H1 | 한배곳 1 |
| grade | H2 | 한배곳 2 |
| grade | H3 | 한배곳 3 |
| grade | H4 | 한배곳 4 |
| grade | D1 | 더배곳 1 |
| grade | D2 | 더배곳 2 |
| grade | DJ | 더배곳 진수 |
| status | ATTENDING | 재학 |
| status | LEAVE | 휴학 |
| status | GRADUATED | 졸업 |
| status | COMPLETED | 수료 |
| status | EXPELLED | 제적 |

---

### FR-USER-004 — 사용자 목록을 조회할 수 있다

**표시 필드**: id, login_id, type, korean_name, english_name, grade, status, entrance.year

**상태값 표시 라벨**

| 필드 | 코드값 | 표시 텍스트 |
|------|--------|------------|
| grade | H1 | 한배곳 1 |
| grade | H2 | 한배곳 2 |
| grade | H3 | 한배곳 3 |
| grade | H4 | 한배곳 4 |
| grade | D1 | 더배곳 1 |
| grade | D2 | 더배곳 2 |
| grade | DJ | 더배곳 진수 |
| status | ATTENDING | 재학 |
| status | LEAVE | 휴학 |
| status | GRADUATED | 졸업 |
| status | COMPLETED | 수료 |
| status | EXPELLED | 제적 |

---

### FR-USER-011 — 졸업 대상자 후보 목록을 조회할 수 있다

**표시 필드**: id, degree, name.korean, name.english, student.entrance, student.graduated

**상태값 표시 라벨**

| 필드 | 코드값 | 표시 텍스트 |
|------|--------|------------|
| degree | H1 | 한배곳 1 |
| degree | H2 | 한배곳 2 |
| degree | H3 | 한배곳 3 |
| degree | H4 | 한배곳 4 |
| degree | D1 | 더배곳 1 |
| degree | D2 | 더배곳 2 |
| degree | DJ | 더배곳 진수 |

---

## 교과목 관리 (DG-COURSE)

### FR-COURSE-004 — 교과목 목록을 조회할 수 있다

**표시 필드**: id, domain, code, name.korean, name.english

---

## 개설수업 관리 (DG-LECTURE)

### FR-LECTURE-001 — 개설수업을 등록할 수 있다

**표시 필드**: id, course, user, category, term, classroom, limit, schedule

**상태값 표시 라벨**

| 필드 | 코드값 | 표시 텍스트 |
|------|--------|------------|
| category | ET | 스튜디오/선택 |
| category | RT | 스튜디오/필수 |
| category | EU | 수업/선택 |
| category | RU | 수업/필수 |
| category | EW | 워크숍/선택 |
| category | RW | 워크숍/필수 |
| category | EP | 프로젝트/선택 |
| category | RP | 프로젝트/필수 |
| semester | SPRING | 봄 |
| semester | FALL | 가을 |

---

### FR-LECTURE-003 — 개설수업을 비활성화(폐강)할 수 있다

**불가역 작업 확인 가드**

- 입력 텍스트: `폐강하겠습니다.` / 컴포넌트: `views/admin/academic_manage/lecture/DetailLecture.vue`

---

### FR-LECTURE-004 — 개설수업을 삭제할 수 있다

**불가역 작업 확인 가드**

- 메시지: `삭제하시겠습니까?` / 컴포넌트: `views/admin/academic_manage/lecture/Lecture.vue`

---

### FR-LECTURE-005 — 개설수업 목록을 조회할 수 있다

**표시 필드**: id, course, user, category, term, classroom, limit, approved, applied, enabled

**상태값 표시 라벨**

| 필드 | 코드값 | 표시 텍스트 |
|------|--------|------------|
| category | ET | 스튜디오/선택 |
| category | RT | 스튜디오/필수 |
| category | EU | 수업/선택 |
| category | RU | 수업/필수 |
| category | EW | 워크숍/선택 |
| category | RW | 워크숍/필수 |
| category | EP | 프로젝트/선택 |
| category | RP | 프로젝트/필수 |
| semester | SPRING | 봄 |
| semester | FALL | 가을 |

---

## 수강신청 관리 (DG-REGISTRATION)

### FR-REG-002 — 봄학기 수강신청을 비동기로 처리할 수 있다

**상태값 표시 라벨**

| 필드 | 코드값 | 표시 텍스트 |
|------|--------|------------|
| requestStatus | PENDING | 처리 중 |
| requestStatus | DONE | 처리 완료 |

**비동기 폴링**

- 간격: 3000ms, 종료 조건: `requestStatus != 'PENDING'` / 컴포넌트: `components/Enrolment.vue`

---

### FR-REG-004 — 특정 학기의 수강신청을 일괄 승인할 수 있다

**불가역 작업 확인 가드**

- 메시지: `일괄 등록을 진행하시겠습니까?` / 컴포넌트: `views/admin/academic_manage/lecture/Lecture.vue`

---

### FR-REG-007 — 수강 성적을 처리할 수 있다

**표시 필드**: registration.id, user, passed, recommended, comment

**상태값 표시 라벨**

| 필드 | 코드값 | 표시 텍스트 |
|------|--------|------------|
| passed | true | P |
| passed | false | F |
| passed | null | P/F |

---

### FR-REG-008 — 수강신청 목록을 조회할 수 있다

**표시 필드**: id, user, lecture, status, attendance, timestamp

---

## 출석 관리 (DG-ATTENDANCE)

### FR-ATT-002 — 출석 현황을 조회할 수 있다

**표시 필드**: id, registration, round, status

---

## 강의평가 (DG-EVALUATION)

### FR-EVAL-001 — 강의평가를 등록할 수 있다

**표시 필드**: satisfaction, achievement, positive, negative, comment

---

## 학기 관리 (DG-TERM)

### FR-TERM-001 — 학기 목록을 조회할 수 있다

**표시 필드**: year, semester, status

**상태값 표시 라벨**

| 필드 | 코드값 | 표시 텍스트 |
|------|--------|------------|
| status | READY | 준비 중 |
| status | APPLYING | 수강신청 중 |
| status | PROCEEDING | 학기 중 |
| status | FINISHED | 종강 |
| semester | SPRING | 봄 |
| semester | FALL | 가을 |

**비활성화 조건**

- `!isAdmin || term[year+semester] === 'FINISHED'`

---

### FR-TERM-003 — 학기 상태를 변경할 수 있다

**표시 필드**: year, semester, status

**상태값 표시 라벨**

| 필드 | 코드값 | 표시 텍스트 |
|------|--------|------------|
| status | READY | 준비 중 |
| status | APPLYING | 수강신청 중 |
| status | PROCEEDING | 학기 중 |
| status | FINISHED | 종강 |
| semester | SPRING | 봄 |
| semester | FALL | 가을 |

**비활성화 조건**

- `!isAdmin || term[year+semester] === 'FINISHED'`

**불가역 작업 확인 가드**

- 입력 텍스트: `종강하겠습니다.` / 컴포넌트: `views/admin/academic_manage/operation/Operation.vue` / 적용 조건: FINISHED 상태로 변경 시에만

---

## 공지사항 (DG-NOTICE)

### FR-NOTICE-004 — 공지사항 목록을 조회할 수 있다

**표시 필드**: id, title, timestamp

---

### FR-NOTICE-005 — 공지사항을 단건 조회할 수 있다

**표시 필드**: id, type, title, body, attachment

---

## 학칙 (DG-RULE)

### FR-RULE-004 — 학칙 목록을 조회할 수 있다

**표시 필드**: id, title, timestamp

---

## 학사일정 (DG-SCHEDULE)

### FR-SCHEDULE-004 — 학사일정 목록을 조회할 수 있다

**표시 필드**: id, title, timestamp

---

## 졸업증명서 (DG-CERTIFICATE)

### FR-CERT-001 — 졸업증명서를 일괄 발급할 수 있다

**표시 필드**: id, degree, name.korean, name.english, birth, student.entrance, student.graduated

**상태값 표시 라벨**

| 필드 | 코드값 | 표시 텍스트 |
|------|--------|------------|
| degree | H1 | 한배곳 1 |
| degree | H2 | 한배곳 2 |
| degree | H3 | 한배곳 3 |
| degree | H4 | 한배곳 4 |
| degree | D1 | 더배곳 1 |
| degree | D2 | 더배곳 2 |
| degree | DJ | 더배곳 진수 |

**불가역 작업 확인 가드**

- 메시지: `발급 대상 확인 모달 (선택된 N명의 목록 표시)` / 컴포넌트: `views/admin/certificate/IssueCertificate.vue`

---

## 자료실 (Google Drive 연동) (DG-DRIVE)

### FR-DRIVE-001 — 자료실 파일/폴더 목록을 조회할 수 있다

**표시 필드**: id, name, directory, size, mimeType, created_time

**상태값 표시 라벨**

| 필드 | 코드값 | 표시 텍스트 |
|------|--------|------------|
| directory | true | 폴더 |
| directory | false | 파일 |

---

## 비동기 요청 처리 (DG-REQUEST)

### FR-REQUEST-001 — 비동기 요청 처리 상태를 조회할 수 있다

**표시 필드**: requestID, status

**상태값 표시 라벨**

| 필드 | 코드값 | 표시 텍스트 |
|------|--------|------------|
| status | PENDING | 처리 중 |
| status | DONE | 완료 |

**비동기 폴링**

- 간격: 3000ms, 종료 조건: `status != 'PENDING'` / 컴포넌트: `components/Enrolment.vue (봄학기 수강신청 결과 확인)`

---

## 클라이언트 전용 요구사항 (CLIENT)

### CL-CERT-001 — 재학/수료/제적 상태인 학생만 재학증명서 페이지에 접근할 수 있다

- **라우트 가드**: `/student/certificate/status/*`
- **진입 조건**: 학생 상태가 ATTENDING, COMPLETED, EXPELLED 중 하나이어야 한다 (needs_not_graduated)
- **차단 조건**: 졸업(GRADUATED) 상태이면 페이지 접근 불가

---

### CL-CERT-002 — 졸업 상태인 학생만 졸업증명서 조회 페이지에 접근할 수 있다

- **라우트 가드**: `/student/certificate/graduated/detail`
- **진입 조건**: 학생 상태가 GRADUATED이어야 한다 (needs_graduated)
- **차단 조건**: 재학/수료/제적 상태이면 페이지 접근 불가

---

### CL-CERT-003 — 졸업증명서 발급 대상자 목록을 졸업학기·배움과정·이름으로 클라이언트에서 필터링할 수 있다

- **컴포넌트**: `IssueCertificate.vue`
- **필터 필드**:

| 필드 | 라벨 |
|------|------|
| student.graduated.semester | 졸업학기 |
| student.grade | 배움과정 |
| name.korean | 국문이름 |

---

### CL-REG-001 — 내 수강신청 목록에서 비활성화(폐강)된 수업은 제외된다

- **클라이언트 필터**: `enabledRegistrationList` getter
- **필터 조건**: `lecture.enabled === true`인 수강신청만 표시

---

### CL-PAGINATION-001 — 페이지네이션 경계 알림을 표시할 수 있다

- **적용 범위**: 페이지네이션이 있는 모든 목록 화면 (11개 이상 컴포넌트)
- **동작**:
  - 첫 번째 페이지에서 이전 이동 시 `'첫번째 페이지입니다.'` 알림을 표시한다
  - 마지막 페이지에서 다음 이동 시 `'마지막 페이지입니다.'` 알림을 표시한다

---

## 횡단 관심사 UI 제약 (Cross-Cutting)

### XC-AUTH-001 — 전역 세션 인증 가드

로그인(`POST /api/v1/user/login`)과 자료실 다운로드(`GET /api/v1/drive/download`)를 제외한 모든 엔드포인트는 유효한 세션 인증을 통과해야 한다.

**적용 도메인**: DG-USER, DG-COURSE, DG-LECTURE, DG-REGISTRATION, DG-ATTENDANCE, DG-EVALUATION, DG-TERM, DG-NOTICE, DG-RULE, DG-SCHEDULE, DG-CERTIFICATE, DG-DRIVE, DG-REQUEST

---

### XC-PERM-001 — 역할 기반 접근 제어 (라우터 권한 가드)

역할 기반 접근 제어는 비트마스크 방식으로 구현된다. 라우터 등록 시 `needsPermission`으로 허용 역할을 지정한다.

| 역할 | 비트값 |
|------|--------|
| Admin | 8 |
| Employee | 2 |
| Professor | 4 |
| Student | 1 |
