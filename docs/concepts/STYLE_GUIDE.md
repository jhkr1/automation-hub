# Concepts Book Style Guide

이 문서는 `docs/concepts/` 개념서의 집필 규칙입니다. 일반 독자를 위한 Chapter가 아니며, Repository 사용법이나 현재 구현의 Reference도 아닙니다.

## Book Purpose

- Python 자동화 시스템의 백엔드·소프트웨어 아키텍처 개념을 설명합니다.
- 개념을 먼저 설명하고, `automation-hub` 사례는 마지막에 연결합니다.
- 특정 프로젝트 구조나 프레임워크 사용법을 복사하도록 가르치지 않습니다.
- 이전 Chapter의 문제를 다음 Chapter의 개념으로 연결합니다.

## Chapter Structure

모든 Chapter는 다음 표준 구조와 순서를 사용합니다.

1. `# Chapter N. Title`
2. `## Real World Example`
3. `## Why Does It Exist?`
4. `## Definition`
5. `## Background Knowledge`
6. `## Responsibilities`
7. `## Typical Workflow`
8. `## Relationship with Other Concepts`
9. `## Common Mistakes`
10. `## Best Practices`
11. `## Trade-offs`
12. `## Minimal Python Example`
13. `## Example from automation-hub`
14. `## Checkpoint`
15. `## Summary`
16. `## Related Concepts`
17. `## Related Project Documents`
18. `## Next Chapter`

모든 Chapter는 위 Section 순서를 사용합니다. `Background Knowledge`는 모든 Chapter에서 `Definition`과 `Responsibilities` 사이에 배치하며, 해당 Chapter를 읽는 데 필요한 기존 용어만 최소한으로 설명합니다.

### Real World Example

- Definition보다 먼저 일상적인 상황으로 문제를 보여 줍니다.
- 택배, 도서관, 은행과 같은 익숙한 예시를 3~6줄로 짧게 사용합니다.
- 실제 Repository 구현이나 특정 프레임워크 설명을 이 Section에 넣지 않습니다.

### Minimal Python Example

- 일반적인 개념을 보여 주는 짧고 실행 가능한 Python 예제를 작성합니다.
- 프로젝트의 실제 코드를 복사하지 않으며, 5~25줄을 권장하고 35줄을 넘기지 않습니다.
- Example from automation-hub보다 먼저 배치해 일반 원리와 프로젝트 사례를 구분합니다.
- 초급자용 예제는 핵심 개념 하나만 보여 주며, 필요하지 않은 Protocol, ABC와 Generic을 사용하지 않습니다.
- 예제 앞에는 입력을, 뒤에는 결과를 한두 문장으로 설명합니다.

### Background Knowledge

- 해당 Chapter를 이해하는 데 꼭 필요한 기존 용어만 2~5개 설명합니다.
- 각 용어는 한 줄 정의, 초보자를 위한 쉬운 설명, 현실 예시를 순서대로 제공합니다.
- 용어 사전처럼 나열하지 말고, Chapter를 읽기 위한 준비 단계로 작성합니다.
- 처음 등장하는 영어 용어에는 한국어 뜻을 함께 씁니다.
- 비유는 정확한 정의를 대신하지 않습니다.
- 이후 Chapter에서는 같은 용어를 반복 정의하지 않고 최초 설명 Chapter로 연결합니다.

### Checkpoint

- 독자가 개념을 자신의 말로 설명할 수 있는지 확인하는 설명형 질문 4개를 작성합니다.
- 객관식이나 새로운 지식을 묻는 질문을 사용하지 않습니다.
- 질문은 본문에서 설명한 책임, 경계와 Trade-off를 확인해야 합니다.

### Summary

- Chapter의 핵심을 3~5문장으로 정리합니다.
- `이번 Chapter에서 기억해야 할 것은`처럼 핵심을 회상하는 문장으로 시작합니다.
- 새로운 개념이나 구현 사실을 추가하지 않습니다.
- 다음 학습 질문으로 자연스럽게 이어지도록 작성합니다.

### Next Chapter

- 실제로 존재하는 다음 Chapter를 링크합니다.
- 다음 Chapter가 해결할 질문을 짧게 안내합니다.
- 마지막 Section으로 유지하며, 책에 없는 내용을 예고하지 않습니다.

## Concept and Project Boundary

본문의 중심은 일반적인 개념 설명입니다. 프로젝트 사례는 마지막 `Example from automation-hub` Section에서만 사용합니다.

| 내용 | 설명 위치 |
|---|---|
| 개념의 정의와 원리 | 본문 |
| 일반적인 책임과 실수 | 본문 |
| 일반적인 Trade-off | 본문 |
| 실제 파일과 현재 구현 | `Example from automation-hub` |
| 정확한 Repository 구조 | Package Architecture 링크 |
| 설계 판단이 형성된 과정 | Architecture Handbook 링크 |

프로젝트 예시를 일반 법칙처럼 쓰지 않습니다. Repository에서 확인된 선택은 “이 사례에서는”이라는 범위로 표현합니다.

## Progressive Disclosure

- 문제를 먼저 보여주고 용어를 정의합니다.
- 정의 뒤에 책임과 인접 개념을 설명합니다.
- 구현 예시는 개념을 설명한 뒤에 배치합니다.
- 한 문단에서 새로운 전문 용어를 과도하게 소개하지 않습니다.
- 상세한 Repository 구현은 Package Architecture로 넘깁니다.

## Writing Style

- 짧고 직접적인 문장을 사용합니다.
- 한 문단은 하나의 핵심 메시지만 전달합니다.
- 일반론은 과장하지 않고 조건과 Trade-off를 함께 설명합니다.
- 특정 프레임워크나 저장소 기술에 종속된 설명은 개념 자체와 분리합니다.
- `Collector`, `Parser`, `Domain Model`처럼 제목에 사용한 용어는 문서 전체에서 일관되게 사용합니다.

## Tables

표는 실제 비교나 책임 구분이 문장보다 명확해질 때 사용합니다.

- Responsibilities는 해야 하는 일과 하면 안 되는 일을 비교합니다.
- Relationship은 인접 개념의 차이를 비교합니다.
- Trade-offs는 선택, 장점, 단점을 비교합니다.
- 한 표에 너무 많은 개념을 넣지 않습니다.

## Mermaid

각 Chapter는 핵심 흐름을 설명하는 Mermaid Diagram을 하나 이상 포함합니다.

- GitHub 기본 Mermaid 문법만 사용합니다.
- `flowchart`, `sequenceDiagram` 등 메시지에 맞는 유형을 선택합니다.
- 하나의 Diagram에는 하나의 핵심 질문만 담습니다.
- `classDef`, `style`, HTML label과 색상을 사용하지 않습니다.
- 제목이나 Section 목록을 단순히 반복하는 Diagram은 만들지 않습니다.

## Links and Navigation

- 실제로 존재하는 문서만 링크합니다.
- 아직 작성되지 않은 Planned Chapter에는 링크를 만들지 않습니다.
- `Related Concepts`는 개념서 안의 다음 학습 대상을 연결합니다.
- `Related Project Documents`는 프로젝트 사실을 확인할 기준 문서를 연결합니다.
- Chapter가 추가되면 이전 Chapter의 마지막에 다음 개념으로 가는 링크를 추가합니다.
- Chapter 1~20은 실제 다음 Chapter 파일을 링크합니다.
- Chapter 21은 마지막 Chapter임을 밝히고 Concepts Book README로 연결합니다.
- 절대 경로와 `file://` 링크를 사용하지 않습니다.

## Beginner-first Writing

- 쉬운 설명을 먼저 제시한 뒤 정확한 기술 용어를 설명합니다.
- 한 문장에 새로운 전문 용어를 여러 개 넣지 않습니다.
- 추상 명사만으로 개념을 설명하지 않고 짧은 예를 함께 사용합니다.
- 프로젝트 사례는 `Example from automation-hub` Section에만 둡니다.

### Two-stage Code Examples

각 Chapter는 가능한 경우 일반 예제와 실제 Repository 예제를 구분합니다.

- `Minimal Python Example`: Repository에 의존하지 않고 핵심 개념 하나를 가장 작게 보여 줍니다.
- `Example from automation-hub`: 실제 코드의 연속된 일부를 발췌하고, 개념과 책임의 연결을 설명합니다.

### Source Accuracy

- 실제 Repository에 존재하는 코드만 발췌합니다.
- 함수명과 변수명을 임의로 바꾸지 않습니다.
- 발췌 코드 바로 아래에 상대 경로 Source 링크를 제공합니다.
- 현재 구현되지 않은 개념은 가상의 코드로 만들지 않고, 구현되지 않았다고 명시합니다.
- API Key, credential, URL credential과 긴 설정·migration 전문은 포함하지 않습니다.

### Code Excerpt Length

- 실제 코드 발췌는 기본 5~20줄로 제한합니다.
- Chapter당 기본 1개, 꼭 필요한 경우에만 최대 2개를 사용합니다.
- 긴 함수 전체를 복사하지 않고, 개념을 보여 주는 연속된 부분만 선택합니다.
- 코드 뒤에는 무엇을 하는지, 왜 이 개념인지, 무엇을 하지 않는지를 설명합니다.

Background Knowledge에는 프로젝트 파일 위치나 구현 여부를 반복해서 적지 않습니다. 실제 파일·클래스·함수와 현재 구현의 한계는 `Example from automation-hub`가 소유합니다.

## Metadata

Chapter와 README에 `예상 읽기 시간`을 추가하지 않습니다. 독자의 읽는 속도보다 학습 목표와 다음 학습 경로를 우선합니다.

## Chapter Navigation

### Heading Anchor

- 각 Chapter의 첫 H1 제목이 GitHub Heading Anchor의 기준이 됩니다.
- Chapter 사이의 링크는 `filename.md#chapter-N-title` 형식을 사용합니다.
- Anchor는 제목의 소문자 변환, 공백의 하이픈 변환과 문장부호 제거라는 GitHub 규칙을 따릅니다.

### Next Chapter

- Chapter 1~20은 실제 다음 Chapter의 Heading Anchor로 연결합니다.
- Chapter 21은 [Concepts Book README](README.md#python-automation-architecture-concepts)로 돌아갑니다.
- 링크 앞에 다음 Chapter를 읽는 이유를 한두 문장으로 설명합니다.

### Bottom Navigation

- 각 Chapter 마지막에 `이전 Chapter | 목차 | 다음 Chapter` 표를 둡니다.
- Chapter 1의 이전 항목은 `처음`, Chapter 21의 다음 항목은 `마지막`으로 표시합니다.
- 이전·다음 Chapter 링크에는 모두 대상 H1의 Heading Anchor를 붙입니다.

## Canonical Boundaries

| 주제 | 기준 문서 |
|---|---|
| 개념 정의와 일반 원리 | `docs/concepts/` |
| 현재 Package 설계 | `docs/packages/*/architecture.md` |
| 실행 방법과 현재 기능 | `docs/packages/*/README.md` |
| Repository 전체 Architecture | `docs/architecture.md` |
| 설계 판단의 형성 과정 | `docs/handbook/` |
| 시간순 개발 기록 | `docs/development/DEV_LOG.md` |

개념서에서 현재 구현의 상세를 반복하지 않습니다. 반대로 Package Architecture에서 일반 개념을 길게 강의하지 않습니다.

## Review Checklist

- [ ] Chapter가 앞 Chapter의 질문에서 자연스럽게 이어지는가?
- [ ] Definition이 처음 읽는 독자에게 명확한가?
- [ ] 개념 설명이 프로젝트 설명보다 많은가?
- [ ] 책임과 책임 밖의 일을 구분했는가?
- [ ] 인접 개념과의 차이를 설명했는가?
- [ ] Mermaid가 실제 이해를 돕는가?
- [ ] 프로젝트 예시가 마지막에 짧게 배치되었는가?
- [ ] Package Architecture와 중복되는 상세 구현이 없는가?
- [ ] Related Concepts와 Project Documents 링크가 유효한가?
