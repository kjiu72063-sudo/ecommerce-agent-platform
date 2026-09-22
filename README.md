# 鐢靛晢 AI Agent 鐢熸€佺郴缁?

杩欐槸涓€涓凡缁忓紑鍙戝埌 B3 闃舵鐨勫鏅鸿兘浣撳钩鍙板熀纭€椤圭洰锛屼笉鏄粠闆跺紑濮嬬殑鐢熶骇绯荤粺銆傚綋鍓嶅唴瀹瑰寘鍚绾﹁祫浜с€佸熀纭€璁炬柦鍘熷瀷銆佹湰鍦?SQLite 闂幆銆佹祴璇曘€佸疄鐜版枃妗ｅ拰鏁欏/鍘嗗彶鏉愭枡銆?

## 褰撳墠闃舵

| 闃舵 | 鍐呭 | 褰撳墠鐘舵€?|
|---|---|---|
| B0 | Agent Platform 濂戠害銆丣SON Schema銆丳ydantic 妯″瀷銆佺姸鎬佹満鍜岀ず渚?| 宸茬撼鍏ユ牴绾у寘锛涘彂甯冩敹鏁涗粛鍦ㄨ繘琛?|
| B1 | 鑳藉姏娉ㄥ唽涓績銆佷緷璧栬В鏋愩€佸唴瀛?SQLite 浠撳偍銆丗astAPI 鍘熷瀷 | 鏈湴闂幆锛涙湭鎵胯鐢熶骇閮ㄧ讲 |
| B1 鍞墠 QA锛圴1 鍒囩墖锛?| 纭畾鎬ф绱⑩啋涓婁笅鏂団啋鍥炵瓟鈫掑缃?鐨勫彧璇诲敭鍓嶉棶绛旓紱绉熸埛闅旂銆佸箓绛夌姸鎬佹満銆丼QLite 鎸佷箙鍖栥€?0 澶╀繚鐣欍€丅1 瀹氫箟瑁呴厤 | 宸蹭氦浠?`src/presale` |
| B2 | Task銆丄gentRun銆丒vent銆丆heckpoint 鍜?SQLite 鎸佷箙鍖?| 鏈湴闂幆锛涙湭鎵胯鍒嗗竷寮忎竴鑷存€?|
| B3 | 纭畾鎬?Context 缁勮銆佸幓閲嶃€佹帓搴忓拰棰勭畻鏍￠獙 | 鏈€灏忛棴鐜?|
| B4鈥揃6 | Harness銆丩oop銆佷笟鍔?Agent | 灏氭湭瀹炵幇 |

## 鐜鍒濆鍖?

瑕佹眰 Python 3.11鈥?.13 鍜?[uv](https://docs.astral.sh/uv/)銆?

```bash
uv sync --extra test --extra quality
```

鎵€鏈夊懡浠や粠椤圭洰鏍圭洰褰曟墽琛岋紝涓嶉渶瑕佹墜宸ヨ缃?`PYTHONPATH`銆?

## 娴嬭瘯涓庤川閲忛棬绂?

```bash
uv run pytest -q            # CI 寮哄埗
uv run ruff check src       # CI 寮哄埗
uv run ruff format --check src                          # CI 寮哄埗
uv run pyright              # CI 寮哄埗锛坰rc/presale + src/agent_runtime锛?
uv run pre-commit run --all-files   # 鏈湴閽╁瓙锛岄潪 CI 寮哄埗
```

褰撳墠鍩虹嚎锛氬叏閲忔祴璇?334 passed锛堜互 `寮€鍙戞枃妗?09-璐ㄩ噺鍩虹嚎涓庨棬绂佸彴璐?md` 鐨勫甫鏃ユ湡鍙拌处涓哄噯锛夈€侰I 閫氳繃 GitHub Actions锛坄.github/workflows/ci.yml`锛夊湪 `main` 涓庢瘡涓?PR 涓婅繍琛岄棬绂侊紙ruff check/format src + pyright + pytest锛夊苟甯?`concurrency` 鍙栨秷鏃?run銆備粨搴撳凡鍏紑锛宍main` 鍚敤鍒嗘敮淇濇姢锛氱洿鎺?寮哄埗鎺ㄩ€佷笌鍒犻櫎琚锛堝惈绠＄悊鍛橈級銆佸繀椤昏蛋 PR銆佽姹?CI 閫氳繃銆佸己鍒剁嚎鎬у巻鍙测€斺€斿悎骞剁邯寰嬬敱骞冲彴寮哄埗銆傛祴璇曡鑼冨叆鍙ｄ綅浜?`tests/b1`銆乣tests/b2`銆乣tests/b3`锛涙棫 B 鐩綍涓殑娴嬭瘯淇濈暀浣滈樁娈佃縼绉诲弬鑰冿紝涓嶅啀浣滀负鏍圭骇榛樿鏀堕泦鍏ュ彛銆?

## 杩愯 QA 鏈嶅姟

鍚屾鍞墠闂瓟鏈嶅姟锛團astAPI锛夈€傞厤缃粡鐜鍙橀噺锛堣 `.env.example`锛夛細
```bash
export PRESALE_CATALOG=./catalog.json        # 鍟嗗搧鐭ヨ瘑锛圝SON 鏁扮粍锛?
# 鍙€夛細鐪熷疄 LLM / 澶栭儴妫€绱?/ SQLite 鎸佷箙鍖?
export PRESALE_LLM_BASE_URL=...; export PRESALE_LLM_MODEL=...; export PRESALE_LLM_API_KEY=...
# export PRESALE_RETRIEVAL_BASE_URL=... ; export PRESALE_DB=./presale.sqlite3
presale-qa-api            # 榛樿 127.0.0.1:8000锛堝彲鐢?PRESALE_QA_HOST/PRESALE_QA_PORT 鏀癸級
```
绔偣锛歚POST /api/v1/presale/qa`锛坆ody: question/product_id/tenant_id/idempotency_key锛夆啋 杩斿洖 `format_outcome`锛堢粓鎬?+ 绛旀 + 璇佹嵁锛夛紱`GET /api/v1/presale/qa/health`銆?

## 澶栭儴妫€绱紙Qdrant锛屽彲閫夛級

鍚戦噺搴撶敤**鏈湴 Qdrant锛圖ocker锛?*锛宔mbedding 澶嶇敤 LLM 鎻愪緵鏂?`/embeddings` 鎴栫嫭绔嬨€傛楠わ紙鍩虹璁炬柦缁熶竴鐢?`docker compose`/Makefile锛岃 `deploy/README.md`锛夛細
1. 璧锋湇鍔★細`docker compose up -d`锛堝惈 Qdrant + Milvus锛?
2. 绱㈠紩锛?
   ```bash
   make index-qdrant   # = PRESALE_QDRANT_URL=http://localhost:6333 PRESALE_EMBEDDING=deterministic presale-index ./catalog.json
   ```
3. 杩愯 QA 鏈嶅姟鏃惰 `PRESALE_QDRANT_URL` 鍗崇敤 Qdrant 妫€绱紙鍚﹀垯纭畾鎬э級銆?

鎼滅储鎸?`tenant_id`/`product_id` 杩囨护锛岃法绉熸埛涓嶆硠婕忥紱澶栭儴妫€绱㈠け璐ュ彲闄嶇骇锛坄RETRIEVAL_DEGRADED`锛夋垨鏄惧紡鎶ラ敊銆?

## 澶栭儴妫€绱紙Hybrid RAG锛孯AG 闃舵 1锛屽彲閫夛級

绋犲瘑锛坆ge-large-zh-v1.5 鈫?Milvus锛? 璇嶆硶锛圔M25锛? RRF 铻嶅悎銆傝 `寮€鍙戞枃妗?12-RAG鏋舵瀯鏂规.md` 涓?`deploy/README.md`銆?
```bash
docker compose up -d            # 璧?Milvus锛堣繛鍚?etcd/minio锛涘崟鐙８璺?milvus 闇€瑕佸畠浠級
make models                     # 涓€娆℃€э細pip install sentence-transformers锛堟湰鍦?bge锛涘彲璺宠繃/鐢ㄧ‘瀹氭€э級
make index-milvus               # catalog.json 鈫?Milvus锛堝彲鐢?PRESALE_EMBEDDING=deterministic 鍏堥獙璇佺閬擄級
# 杩愯 QA 鏈嶅姟鏃惰 PRESALE_MILVUS_URI 鍗崇敤 Hybrid 妫€绱?
```
BM25 涓鸿繘绋嬪唴锛圕JK 瀛楃骇鍒嗚瘝锛夛紱Milvus 绋犲瘑鐐规寜 `tenant_id`/`product_id` 杩囨护銆?

## 鐩綍杈圭晫

```text
src/
鈹溾攢鈹€ agent_platform_contracts/  # B0 鍞竴杩愯鏃跺寘鍜屽绾﹁祫浜?
鈹溾攢鈹€ registry/                  # B1 鑳藉姏娉ㄥ唽涓績锛圱ool/Skill/Prompt CRUD + 渚濊禆瑙ｆ瀽锛?
鈹溾攢鈹€ runtime/                   # B2 鐘舵€佷笌鎸佷箙鍖栵紙Task/AgentRun/Event/Checkpoint 鐢熷懡鍛ㄦ湡锛?
鈹溾攢鈹€ context/                   # B3 Context 寮曟搸锛堢粍瑁?鍘婚噸/棰勭畻鏍￠獙锛?
鈹溾攢鈹€ agent_runtime/             # B4 Harness/Loop/Agent 鍙鐢ㄦ墽琛屽眰锛堥潪 B2 runtime锛?
鈹斺攢鈹€ presale/                   # 鍞墠鍟嗗搧闂瓟 V1 涓氬姟鍒囩墖锛堝箓绛?SQLite/RAG/瑁呴厤锛?

tests/                         # 鏍圭骇瑙勮寖娴嬭瘯锛坱ests/b1, tests/b2, tests/b3锛?
B0-濂戠害鍩虹/contracts/          # B0 濂戠害鍖呮潵婧愪笌浜や粯鏉愭枡
B0-濂戠害鍩虹/浠庨浂瀹炵幇/            # 鍘嗗彶/鏁欏瀹炵幇锛屼笉鏄繍琛屾椂鏉冨▉鏉ユ簮
寮€鍙戞枃妗?                       # 璁捐銆佸疄鐜板拰闃舵鎸囧崡
```

`B0-濂戠害鍩虹/contracts/...` 涓殑鐗堟湰鍖栧绾﹀寘鏄綋鍓嶆潈濞佹潵婧愶紱鏍圭骇 `src/agent_platform_contracts` 鏄叾 monorepo 瀹夎甯冨眬銆傚绾﹁祫浜ч€氳繃 `agent_platform_contracts.assets_api.asset_path()` 璁块棶锛屼笉搴斾緷璧栨簮鐮佺粷瀵硅矾寰勩€?

## 宸ョ▼绾︽潫

- 濂戠害浼樺厛锛氬疄鐜板繀椤婚伒瀹?B0 妯″瀷銆丼chema 鍜岀姸鎬佹満銆?
- 娴嬭瘯椹卞姩锛氬彉鏇村厛琛ユ祴璇曪紝鍐嶄慨鏀瑰疄鐜般€?
- 闃舵闅旂锛欱4 涔嬪墠涓嶅紩鍏ユā鍨嬭皟鐢ㄣ€佸畬鏁?Harness 鎴?Loop 绛栫暐銆?
- 鏈湴杈圭晫锛氬綋鍓嶅彧鎵胯鍗曡繘绋嬫湰鍦板唴瀛?SQLite 闂幆锛屼笉鎵胯 PostgreSQL銆佹秷鎭槦鍒椼€佸垎甯冨紡浜嬪姟鎴栧杩涚▼涓€鑷存€с€?
- 涓嶆妸 `B0-濂戠害鍩虹/浠庨浂瀹炵幇/` 褰撲綔鏂颁唬鐮佷緷璧栵紱瀹冪敤浜庢暀瀛︺€佸巻鍙茶拷婧拰瀵圭収銆?

## 璐＄尞涓庣淮鎶?

- 寮€鍙戞祦绋嬨€侀棬绂佷笌鍒嗘敮/PR 瑙勮寖瑙?[`CONTRIBUTING.md`](CONTRIBUTING.md)銆?
- 鍚庡彴缁存姢锛?0 澶╀繚鐣欏綊妗ｏ級鐨勮皟搴﹀叆鍙ｏ紙HTTP 绔偣 + CLI锛夎 [`寮€鍙戞枃妗?09-璐ㄩ噺鍩虹嚎涓庨棬绂佸彴璐?md`](寮€鍙戞枃妗?09-璐ㄩ噺鍩虹嚎涓庨棬绂佸彴璐?md)銆?








