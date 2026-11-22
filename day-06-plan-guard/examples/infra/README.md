# 예제 plan 을 어떻게 만들었나 (그대로 재현 가능)

여기 있는 `../proposal-plan.json`, `../fixed-plan.json` 은 **손으로 쓴 JSON 이 아니다.**
terraform 1.9.8 이 실제로 계산한 plan 을 `terraform show -json` 으로 뽑은 것이다.

```bash
# 1) terraform 1.9.8 + AWS provider 3.76.1
curl -LO https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_linux_amd64.zip
# (압축 풀고 PATH 에)

mkdir infra && cd infra
# 2) prior-state.json 을 terraform.tfstate 로 두고 init
cp ../examples/infra/prior-state.json terraform.tfstate
terraform init            # hashicorp/aws 3.76.1

# 3) 제안서(proposal.tf)로 plan
cp ../examples/infra/proposal.tf main.tf
terraform plan -refresh=false -out=tfplan
terraform show -json tfplan > proposal-plan.json

# 4) 리뷰 후 고친 것(fixed.tf)으로 다시 plan — state 는 그대로
cp ../examples/infra/fixed.tf main.tf
terraform plan -refresh=false -out=tfplan2
terraform show -json tfplan2 > fixed-plan.json
```

## 정직하게 밝히는 것

- **state 는 손으로 만들었다.** `prior-state.json` 은 provider 스키마(`terraform providers schema -json`)의
  속성 타입에 맞춰 '이미 돌고 있는 인프라'를 흉내 낸 것이다. 실제 AWS 계정의 state 가 아니다.
  (AWS 자격 증명 없이 plan 을 만들기 위한 선택이다 — plan 계산 자체는 terraform 이 한다.)
- **provider 는 자격 증명 확인을 건너뛰게 했다.** `skip_credentials_validation`, `skip_requesting_account_id`,
  `skip_metadata_api_check` 를 켰다. plan 은 API 를 부르지 않으므로 결과 값은 설정과 state 로만 결정된다.
- **`-refresh=false`** 로 만들었다. 그래서 실제 인프라와 state 가 어긋난 경우(drift)는 이 plan 에 없다.
- 제안서 plan 에는 예제용 비밀번호(`correcthorsebatterystaple`)가 들어 있다.
  이 값이 plan 파일 세 곳에 평문으로 나오는 것이 `redact` 기능의 실제 근거다.
