# B4鈥揃6 Harness / Loop / Agent 瑙勬牸

> 閲岀▼纰戯細鏈€灏忓彲瑙傚療 Agent 闂幆
> 鍩虹嚎锛歏1 + 澶栭儴閫傞厤鍣ㄥ绾﹀凡鏀舵暃锛涢鍩熷缓妯″畬鎴愶紙鍐崇瓥 D-B1..B8锛?
> 璇嶆眹锛氳 `CONTEXT.md`锛涢鍩熸ā鍨嬶細`docs/domain-model-b4b6.md`

## Problem Statement

骞冲彴鐩墠鍙湁涓€涓?鍗曟鍞墠闂瓟"涓氬姟娴侊紙`PresaleQaRunner.ask`锛夈€傚綋骞冲彴闇€瑕佽繍琛屾洿澶氫笟鍔?Agent銆佹垨鍦ㄤ竴娆¤繍琛屽唴杩涜澶氭宸ュ叿寰幆鏃讹紝缂哄皯涓€涓彲澶嶇敤鐨?鎵ц Agent + 鍐崇瓥浣曟椂鍋滄"鐨勯€氱敤灞傘€傛湰杞厛鍋氫竴涓渶灏忓彲瑙傚療鐨勯棴鐜紝鎶婄幇鏈夊敭鍓嶉棶绛斾綔涓虹涓€涓 Harness 椹卞姩鐨?Agent锛屽苟鎶借薄鍑哄彲澶嶇敤鐨?Harness锛堟墽琛屽３锛変笌 Loop锛堝惊鐜喅绛栵級灞傘€?

## Solution

寮曞叆鍙鐢ㄧ殑 Agent 鎵ц涓庡喅绛栧惊鐜眰锛?

- **Harness锛堟墽琛屽３锛?*锛氬垱寤轰竴涓?`AgentRun`锛岀敤鍙敞鍏ョ殑 Agent 瀹炰緥鎵ц涓氬姟姝ラ锛屾毚闇插彧璇诲伐鍏凤紙`retrieve`锛夛紝鎶婃墽琛屾媶鎴?`AgentStep` 骞惰褰?`ToolCall`/`Event`锛岃繑鍥炲彲瑙傚療杈撳嚭銆?
- **Loop锛堝惊鐜喅绛栵級**锛氭瘡涓?`AgentStep` 鍚庡喅绛?`continue` / `finalize` / `need_human`锛屽彈 `max_steps` 绾︽潫銆?
- 棣栧疄渚嬶細澶嶇敤鐜版湁鍞墠 QA 浣滀负 Agent锛沗retrieve` 宸ュ叿澶嶇敤 `RetrievalPort` 濂戠害锛堝彧璇伙級銆?
- 鍚屾銆佽姹傚唴鐩磋繛锛涙湰杞?`continue` 鍗曟缁堟€侊紙澶氭閲嶆煡鐣欏緟鍚庣画鍔犲伐鍏凤級銆?

## User Stories

1. 浣滀负鍐呴儴瀹㈡湇杩愯惀锛屾垜鎯虫彁浜や竴涓敭鍓嶉棶棰橈紝浣垮叾缁?Harness 鎵ц骞跺緱鍒颁竴涓彲瑙傚療鐨勭粓鎬侊紙杈撳嚭鎴栬浆浜哄伐锛夛紝浠ヤ究鎴戣兘纭畾鏈杩愯宸插畬鎴愩€?
2. 浣滀负瀹㈡湇杩愯惀锛屾垜鎯冲湪鏃犺瘉鎹?璇佹嵁鍐茬獊鏃剁湅鍒?`need_human` 缁堟€侊紝浠ヤ究鎴戠煡閬撻渶瑕佷汉宸ュ鏍革紝鑰屼笉鏄褰?绯荤粺澶辫触"銆?
3. 浣滀负瀹㈡湇杩愯惀锛屾垜鎯崇湅鍒版湰娆?`AgentRun` 鐨勬楠ゆ暟銆佹墍鐢ㄥ伐鍏蜂笌鏈€缁堝喅绛栵紝浠ヤ究鎴戣兘杩芥函涓€娆¤繍琛屽浣曡蛋鍒扮粓鎬併€?
4. 浣滀负骞冲彴寮€鍙戣€咃紝鎴戞兂鐢ㄤ竴涓€氱敤 Harness 椹卞姩涓嶅悓 Agent 瀹炰緥锛屼互渚挎柊涓氬姟 Agent 鑳藉鐢ㄦ墽琛屽３涓庡伐鍏锋敞鍐岃€屼笉閲嶅啓銆?
5. 浣滀负骞冲彴寮€鍙戣€咃紝鎴戞兂鐢ㄤ竴涓彲閰嶇疆鐨?Loop 鍐崇瓥绛栫暐锛堝惈 `max_steps`锛夛紝浠ヤ究鎺у埗涓€娆¤繍琛岀殑涓婇檺銆侀槻姝㈠け鎺с€?
6. 浣滀负骞冲彴寮€鍙戣€咃紝鎴戞兂璁?`retrieve` 鍙墽琛屽彧璇荤煡璇嗘煡璇紝浠ヤ究鏈疆涓嶅紩鍏ユ湁鍓綔鐢ㄧ殑宸ュ叿銆?
7. 浣滀负瀹㈡湇杩愯惀锛屾垜鎯冲悓涓€闂鐨勯噸澶嶆彁浜や繚鎸佸箓绛夛紙鍚?key 鍚岀粨鏋滐級锛屼互渚块噸璇曚笉浜х敓閲嶅鎵ц銆?
8. 浣滀负瀹㈡湇杩愯惀锛屾垜鎯?`need_human` 鍗崇粓鎬侊紙涓嶇户缁惊鐜級锛屼互渚垮凡闇€浜哄伐鏃朵笉浼氱┖杞洿澶氭楠ゃ€?

## Implementation Decisions

- 鏂板妯″潡锛堥€昏緫鑱岃矗锛屼笉鎸囧叿浣撴枃浠惰矾寰勶級锛?
  - `Harness`锛氭寔鏈変竴涓伐鍏烽泦銆侀┍鍔ㄤ竴涓?`AgentRun`銆佹妸鎵ц鎷嗘垚 `AgentStep`銆佽褰?`ToolCall`/`Event`銆佹毚闇叉瘡姝ュ彲瑙傚療杈撳嚭銆?
  - `Loop`锛歚decide(step, step_count) -> continue | finalize | need_human`锛屽彈 `max_steps`锛堥粯璁?5锛夌害鏉熴€?
  - `Tool`锛坄retrieve`锛夛細鍖呰 `RetrievalPort`锛屽彧璇伙紱璋冪敤浜х敓涓€涓?`ToolCall` 璁板綍銆?
  - Agent 瀹炰緥锛氬寘瑁呯幇鏈夊敭鍓?QA锛坄PresaleQaRunner`锛変负涓€涓?鍗曟涓氬姟鎵ц + need_human 淇″彿"鐨?Agent銆?
- 鍒嗗眰鍖呰锛堝喅绛?D-B6锛夛細Harness 鍦ㄥ叾澶栧眰缂栨帓涓€涓?`AgentRun`锛沗PresaleQaRunner.ask` 鍐呴儴涓氬姟娴佷笉鍙樸€?
- 缁堟€佽涔夛紙D-B2锛夛細`need_human` 鍗崇粓鎬侊紱`max_steps` 杈惧埌鍗崇粓鎬侊紱`finalize` 涓烘甯歌緭鍑虹粓鎬併€?
- 鏈疆 `continue` 鍗曟缁堟€侊紙D-B4锛夛細鍐崇瓥绛栫暐瀛樺湪 `continue` 鍒嗘敮锛屼絾鍦ㄥ綋鍓嶅伐鍏烽泦涓嬩笉瑙﹀彂锛涘姝ラ噸鏌ョ暀寰呭悗缁姞宸ュ叿銆?
- 骞傜瓑锛堟部鐢級锛氬悓 key 閲嶆斁杩斿洖宸叉寔涔呯粨鏋滐紱Harness 澶嶇敤瀹冩墍鍦ㄨ繍琛屽眰宸叉湁鐨勫箓绛変繚璇侊紝涓嶅彟閫犱竴濂椼€?
- 鏃跺簭锛氬悓姝ャ€佽姹傚唴鐩磋繛锛圖-B7锛夈€傛棤澶栭儴鍓綔鐢ㄥ伐鍏凤紙D-B8锛夈€?

## Testing Decisions

- 濂芥祴璇曞彧娴嬪閮ㄨ涓猴紙`Harness.execute` 鐨勫彲瑙傚療杈撳嚭锛夛紝涓嶆祴鍐呴儴瀹炵幇缁嗚妭銆?
- 涓绘祴璇曟帴缂濓細`Harness.execute(question, agent)` 鈥斺€?鐢ㄧ湡瀹炲敭鍓?QA 瀹炰緥 + 鍙敞鍏?`retrieve` 宸ュ叿 + 鍙厤缃?Loop 椹卞姩锛屾柇瑷€锛?
  - 缁堟€佸喅绛栨纭紙matched鈫抐inalize锛沶o_evidence/conflict鈫抧eed_human锛夛紱
  - 姝ユ暟 鈮?max_steps锛?
  - `retrieve` 宸ュ叿璋冪敤琚褰曚负 `ToolCall`锛?
  - `need_human` 鍗崇粓鎬併€佷笉鍐嶇户缁紱
  - 鍚?key 骞傜瓑锛堥噸鏀惧悓缁撴灉锛夈€?
- 澶嶇敤鏃㈡湁娴嬭瘯鍏堜緥锛歚tests/b1/test_external_ports.py`锛堟敞鍏?transport 鐨勫绾?闆嗘垚娴嬭瘯锛夈€乣tests/b1/test_idempotency_state.py`锛堝箓绛夌姸鎬佹柇瑷€锛夈€傚彲娉ㄥ叆 fake `retrieve` 宸ュ叿涓?fake Loop 绛栫暐銆?
- 澶辫触/闄嶇骇璇箟澶嶇敤 `RetrievalPort` 宸插畾濂戠害锛圫lice 3锛歚RetrievalError` / `RETRIEVAL_DEGRADED`锛夈€?

## Out of Scope

- 澶氭宸ュ叿寰幆鐨?`continue` 瑙﹀彂涓庡宸ュ叿缂栨帓銆?
- 鏂板鏈夊壇浣滅敤鐨勫伐鍏凤紙涓嬪崟/鏀逛环/鍐欏簱瀛橈級銆?
- 寮傛闃熷垪/鍥炶皟銆?
- 鏂颁笟鍔?Agent锛堥櫎鍞墠闂瓟涔嬪锛夈€?
- 鐪熷疄澶栭儴妫€绱?鍚戦噺搴撴帴绾匡紙浠嶆部鐢ㄥ彲娉ㄥ叆 transport锛岄€夊瀷鐣欏緟鍚庣画锛夈€?

## Further Notes

- `max_steps` 榛樿 5锛堝喅绛?D-B5锛夛紱鏄惁闇€瑕佽繍琛屾椂鍙厤缃暀寰?ticket 闃舵瀹氥€?
- 鍐崇瓥淇″彿鏉ユ簮锛氭湰杞负 AgentStep 鐨?`need_human` + 姝ユ暟璁℃暟锛涚疆淇″害椹卞姩鐣欏緟鍚庣画銆?
- **`CONTINUE` 鍒嗘敮鐘舵€?*锛歚Loop.decide` 鐨?`CONTINUE` 杩斿洖鍊肩粨鏋勬€у瓨鍦ㄤ絾褰撳墠姘镐笉瑙﹀彂鈥斺€旈粯璁?`Loop` 瀹炵幇瀵归潪 `need_human` 姝ラ鐩存帴 `FINALIZE`銆傚姝ュ伐鍏峰惊鐜殑 `continue` 瑙﹀彂銆佸彲閰嶇疆杩唬绛栫暐锛坰ingle_pass/react/repair/ralph锛夊睘浜?**B5 Loop 寮曟搸** 鑼冨洿锛屼笉鍦ㄦ湰 Harness 鏈€灏忛棴鐜寖鍥村唴銆?
- 鍙戝竷鍒?issue tracker 鏃舵墦 `ready-for-agent` 鏍囩銆?
