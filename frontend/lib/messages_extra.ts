// Additional UI strings (signup form, translation page, progress dashboard). Merged over messages.ts.
// NOTE: non-English strings are AI-drafted and have NOT been reviewed by native speakers.
type Dict = Record<string, string>;

const en: Dict = {
  "nav.translate": "Translate",
  "auth.name": "Name", "auth.identifier": "Username or email", "auth.confirm": "Confirm password", "auth.role": "Role", "auth.prefLang": "Preferred language",
  "auth.demoAs": "Demo accounts — click to sign in (password “demo”)", "auth.protoRole": "Prototype: role self-selection is enabled. Self-registered educators are never counted as independent validation.",
  "auth.hint.identifier": "A username (3–32 letters, digits, underscore) or an email address",
  "err.name_required": "Please enter your name.", "err.invalid_email": "Please enter a valid email address.", "err.password_mismatch": "Passwords do not match.",
  "err.translation_unavailable": "Translation is not available right now (model missing or provider not configured).", "err.same_language": "Choose two different languages.",
  "err.required": "Please fill in all required fields.", "err.model_unavailable": "A required model is unavailable on the server.",
  "coach.sampleNext": "Insert sample", "coach.textLangNote": "This is the language of the text you write. The interface language is chosen at the top right.",
  "tr.title": "Translate", "tr.subtitle": "Machine translation between languages. This is separate from grammar correction.", "tr.source": "From", "tr.target": "To", "tr.input": "Text to translate",
  "tr.placeholder": "Type or paste text…", "tr.button": "Translate", "tr.working": "Translating… (first request loads the model)", "tr.output": "Translation", "tr.swap": "Swap languages",
  "tr.provider": "Provider: {p} · model: {m}", "tr.license": "Model licence: {l} (non-commercial).", "tr.note": "Machine translation can contain errors; Odia and Telugu are lower-resource and less reliable.",
  "prog.corrections": "Total corrections", "prog.corrected": "Corrected sentences", "prog.avgConf": "Average confidence (uncalibrated)", "prog.acceptRate": "Suggestion acceptance",
  "prog.activity": "Activity — last 14 days", "prog.byLanguage": "Activity by language", "prog.recentHistory": "Recent corrections", "prog.errorsByType": "Errors by type",
  "prog.empty": "You have no corrections yet. Go to the Coach page, write a sentence and press “Correct Text”.", "prog.goCoach": "Open Coach", "prog.none": "—", "prog.original": "Original", "prog.correctedText": "Corrected (O2)",
};

const te: Dict = {
  "nav.translate": "అనువాదం",
  "auth.name": "పేరు", "auth.identifier": "వినియోగదారు పేరు లేదా ఇమెయిల్", "auth.confirm": "పాస్‌వర్డ్ నిర్ధారించండి", "auth.role": "పాత్ర", "auth.prefLang": "ప్రాధాన్య భాష",
  "auth.demoAs": "డెమో ఖాతాలు — సైన్ ఇన్ కోసం క్లిక్ చేయండి (పాస్‌వర్డ్ “demo”)", "auth.protoRole": "ప్రోటోటైప్: పాత్రను స్వయంగా ఎంచుకోవచ్చు. స్వయంగా నమోదైన అధ్యాపకులు స్వతంత్ర ధృవీకరణగా లెక్కించబడరు.",
  "auth.hint.identifier": "వినియోగదారు పేరు (3–32 అక్షరాలు, అంకెలు, అండర్‌స్కోర్) లేదా ఇమెయిల్ చిరునామా",
  "err.name_required": "దయచేసి మీ పేరు నమోదు చేయండి.", "err.invalid_email": "దయచేసి సరైన ఇమెయిల్ చిరునామా ఇవ్వండి.", "err.password_mismatch": "పాస్‌వర్డ్‌లు సరిపోలడం లేదు.",
  "err.translation_unavailable": "అనువాదం ప్రస్తుతం అందుబాటులో లేదు (మోడల్ లేదు లేదా ప్రొవైడర్ కాన్ఫిగర్ కాలేదు).", "err.same_language": "రెండు వేర్వేరు భాషలను ఎంచుకోండి.", "err.required": "దయచేసి అన్ని తప్పనిసరి ఫీల్డ్‌లను పూరించండి.", "err.model_unavailable": "సర్వర్‌లో అవసరమైన మోడల్ అందుబాటులో లేదు.",
  "coach.sampleNext": "నమూనా చొప్పించు", "coach.textLangNote": "ఇది మీరు రాసే టెక్స్ట్ భాష. ఇంటర్‌ఫేస్ భాషను కుడి పైన ఎంచుకోండి.",
  "tr.title": "అనువాదం", "tr.subtitle": "భాషల మధ్య యంత్ర అనువాదం. ఇది వ్యాకరణ దిద్దుబాటుకు భిన్నం.", "tr.source": "నుండి", "tr.target": "కు", "tr.input": "అనువదించాల్సిన టెక్స్ట్",
  "tr.placeholder": "టెక్స్ట్ టైప్ చేయండి లేదా అతికించండి…", "tr.button": "అనువదించు", "tr.working": "అనువదిస్తోంది… (మొదటి అభ్యర్థన మోడల్‌ను లోడ్ చేస్తుంది)", "tr.output": "అనువాదం", "tr.swap": "భాషలను మార్చు",
  "tr.provider": "ప్రొవైడర్: {p} · మోడల్: {m}", "tr.license": "మోడల్ లైసెన్స్: {l} (వాణిజ్యేతర).", "tr.note": "యంత్ర అనువాదంలో తప్పులు ఉండవచ్చు; ఒడియా మరియు తెలుగు తక్కువ వనరుల భాషలు, కాబట్టి తక్కువ నమ్మదగినవి.",
  "prog.corrections": "మొత్తం దిద్దుబాట్లు", "prog.corrected": "సరిచేసిన వాక్యాలు", "prog.avgConf": "సగటు విశ్వాసం (క్రమాంకనం లేదు)", "prog.acceptRate": "సూచనల ఆమోద రేటు",
  "prog.activity": "కార్యకలాపం — గత 14 రోజులు", "prog.byLanguage": "భాషల వారీ కార్యకలాపం", "prog.recentHistory": "ఇటీవలి దిద్దుబాట్లు", "prog.errorsByType": "రకం వారీగా తప్పులు",
  "prog.empty": "మీకు ఇంకా దిద్దుబాట్లు లేవు. కోచ్ పేజీకి వెళ్లి, ఒక వాక్యం రాసి “టెక్స్ట్ సరిచేయి” నొక్కండి.", "prog.goCoach": "కోచ్ తెరవండి", "prog.none": "—", "prog.original": "అసలు", "prog.correctedText": "సరిచేసినది (O2)",
};

const or: Dict = {
  "nav.translate": "ଅନୁବାଦ",
  "auth.name": "ନାମ", "auth.identifier": "ଉପଯୋଗକର୍ତ୍ତା ନାମ କିମ୍ବା ଇମେଲ୍", "auth.confirm": "ପାସୱାର୍ଡ ନିଶ୍ଚିତ କରନ୍ତୁ", "auth.role": "ଭୂମିକା", "auth.prefLang": "ପସନ୍ଦର ଭାଷା",
  "auth.demoAs": "ଡେମୋ ଖାତା — ସାଇନ୍ ଇନ୍ ପାଇଁ କ୍ଲିକ୍ କରନ୍ତୁ (ପାସୱାର୍ଡ “demo”)", "auth.protoRole": "ପ୍ରୋଟୋଟାଇପ୍: ଭୂମିକା ନିଜେ ବାଛିହେବ। ନିଜେ ପଞ୍ଜୀକୃତ ଶିକ୍ଷକମାନେ ସ୍ୱାଧୀନ ପ୍ରମାଣୀକରଣ ଭାବେ ଗଣାଯାଆନ୍ତି ନାହିଁ।",
  "auth.hint.identifier": "ଉପଯୋଗକର୍ତ୍ତା ନାମ (3–32 ଅକ୍ଷର, ଅଙ୍କ, ଅଣ୍ଡରସ୍କୋର) କିମ୍ବା ଇମେଲ୍ ଠିକଣା",
  "err.name_required": "ଦୟାକରି ଆପଣଙ୍କ ନାମ ଲେଖନ୍ତୁ।", "err.invalid_email": "ଦୟାକରି ଏକ ବୈଧ ଇମେଲ୍ ଠିକଣା ଦିଅନ୍ତୁ।", "err.password_mismatch": "ପାସୱାର୍ଡ ମେଳ ଖାଉନାହିଁ।",
  "err.translation_unavailable": "ଅନୁବାଦ ବର୍ତ୍ତମାନ ଉପଲବ୍ଧ ନୁହେଁ (ମଡେଲ୍ ନାହିଁ କିମ୍ବା ପ୍ରୋଭାଇଡର୍ ବିନ୍ୟାସିତ ନୁହେଁ)।", "err.same_language": "ଦୁଇଟି ଭିନ୍ନ ଭାଷା ବାଛନ୍ତୁ।", "err.required": "ଦୟାକରି ସମସ୍ତ ଆବଶ୍ୟକ ଘର ପୂରଣ କରନ୍ତୁ।", "err.model_unavailable": "ସର୍ଭରରେ ଆବଶ୍ୟକ ମଡେଲ୍ ଉପଲବ୍ଧ ନୁହେଁ।",
  "coach.sampleNext": "ନମୁନା ଭରନ୍ତୁ", "coach.textLangNote": "ଏହା ଆପଣ ଲେଖୁଥିବା ଟେକ୍ସଟ୍‌ର ଭାଷା। ଇଣ୍ଟରଫେସ୍ ଭାଷା ଉପର ଡାହାଣରେ ବାଛନ୍ତୁ।",
  "tr.title": "ଅନୁବାଦ", "tr.subtitle": "ଭାଷା ମଧ୍ୟରେ ମେସିନ୍ ଅନୁବାଦ। ଏହା ବ୍ୟାକରଣ ସଂଶୋଧନଠାରୁ ଭିନ୍ନ।", "tr.source": "ରୁ", "tr.target": "କୁ", "tr.input": "ଅନୁବାଦ ପାଇଁ ଟେକ୍ସଟ୍",
  "tr.placeholder": "ଟେକ୍ସଟ୍ ଟାଇପ୍ କିମ୍ବା ପେଷ୍ଟ୍ କରନ୍ତୁ…", "tr.button": "ଅନୁବାଦ କରନ୍ତୁ", "tr.working": "ଅନୁବାଦ ହେଉଛି… (ପ୍ରଥମ ଅନୁରୋଧରେ ମଡେଲ୍ ଲୋଡ୍ ହୁଏ)", "tr.output": "ଅନୁବାଦ", "tr.swap": "ଭାଷା ବଦଳାନ୍ତୁ",
  "tr.provider": "ପ୍ରୋଭାଇଡର୍: {p} · ମଡେଲ୍: {m}", "tr.license": "ମଡେଲ୍ ଲାଇସେନ୍ସ: {l} (ଅବାଣିଜ୍ୟିକ)।", "tr.note": "ମେସିନ୍ ଅନୁବାଦରେ ଭୁଲ ଥାଇପାରେ; ଓଡ଼ିଆ ଓ ତେଲୁଗୁ କମ୍ ସମ୍ବଳର ଭାଷା, ତେଣୁ କମ୍ ନିର୍ଭରଯୋଗ୍ୟ।",
  "prog.corrections": "ମୋଟ ସଂଶୋଧନ", "prog.corrected": "ସଂଶୋଧିତ ବାକ୍ୟ", "prog.avgConf": "ହାରାହାରି ବିଶ୍ୱାସ (ଅଙ୍କନାଙ୍କିତ ନୁହେଁ)", "prog.acceptRate": "ପରାମର୍ଶ ଗ୍ରହଣ ହାର",
  "prog.activity": "କାର୍ଯ୍ୟକଳାପ — ଗତ 14 ଦିନ", "prog.byLanguage": "ଭାଷା ଅନୁଯାୟୀ କାର୍ଯ୍ୟକଳାପ", "prog.recentHistory": "ସାମ୍ପ୍ରତିକ ସଂଶୋଧନ", "prog.errorsByType": "ପ୍ରକାର ଅନୁଯାୟୀ ଭୁଲ",
  "prog.empty": "ଆପଣଙ୍କର ଏପର୍ଯ୍ୟନ୍ତ କୌଣସି ସଂଶୋଧନ ନାହିଁ। କୋଚ୍ ପୃଷ୍ଠାକୁ ଯାଇ ଗୋଟିଏ ବାକ୍ୟ ଲେଖି “ଟେକ୍ସଟ୍ ସଂଶୋଧନ କରନ୍ତୁ” ଦବାନ୍ତୁ।", "prog.goCoach": "କୋଚ୍ ଖୋଲନ୍ତୁ", "prog.none": "—", "prog.original": "ମୂଳ", "prog.correctedText": "ସଂଶୋଧିତ (O2)",
};

const hi: Dict = {
  "nav.translate": "अनुवाद",
  "auth.name": "नाम", "auth.identifier": "उपयोगकर्ता नाम या ईमेल", "auth.confirm": "पासवर्ड की पुष्टि करें", "auth.role": "भूमिका", "auth.prefLang": "पसंदीदा भाषा",
  "auth.demoAs": "डेमो खाते — साइन इन के लिए क्लिक करें (पासवर्ड “demo”)", "auth.protoRole": "प्रोटोटाइप: भूमिका स्वयं चुनी जा सकती है। स्वयं पंजीकृत शिक्षक स्वतंत्र सत्यापन नहीं माने जाते।",
  "auth.hint.identifier": "उपयोगकर्ता नाम (3–32 अक्षर, अंक, अंडरस्कोर) या ईमेल पता",
  "err.name_required": "कृपया अपना नाम दर्ज करें।", "err.invalid_email": "कृपया मान्य ईमेल पता दर्ज करें।", "err.password_mismatch": "पासवर्ड मेल नहीं खाते।",
  "err.translation_unavailable": "अनुवाद अभी उपलब्ध नहीं है (मॉडल नहीं है या प्रदाता कॉन्फ़िगर नहीं है)।", "err.same_language": "दो अलग-अलग भाषाएँ चुनें।", "err.required": "कृपया सभी आवश्यक फ़ील्ड भरें।", "err.model_unavailable": "सर्वर पर आवश्यक मॉडल उपलब्ध नहीं है।",
  "coach.sampleNext": "नमूना डालें", "coach.textLangNote": "यह आपके लिखे पाठ की भाषा है। इंटरफ़ेस भाषा ऊपर दाईं ओर चुनें।",
  "tr.title": "अनुवाद", "tr.subtitle": "भाषाओं के बीच मशीन अनुवाद। यह व्याकरण सुधार से अलग है।", "tr.source": "से", "tr.target": "में", "tr.input": "अनुवाद के लिए पाठ",
  "tr.placeholder": "पाठ टाइप या पेस्ट करें…", "tr.button": "अनुवाद करें", "tr.working": "अनुवाद हो रहा है… (पहला अनुरोध मॉडल लोड करता है)", "tr.output": "अनुवाद", "tr.swap": "भाषाएँ बदलें",
  "tr.provider": "प्रदाता: {p} · मॉडल: {m}", "tr.license": "मॉडल लाइसेंस: {l} (गैर-व्यावसायिक)।", "tr.note": "मशीन अनुवाद में त्रुटियाँ हो सकती हैं; ओड़िया और तेलुगु कम संसाधन वाली भाषाएँ हैं, इसलिए कम विश्वसनीय हैं।",
  "prog.corrections": "कुल सुधार", "prog.corrected": "सुधारे गए वाक्य", "prog.avgConf": "औसत विश्वास (अंशांकित नहीं)", "prog.acceptRate": "सुझाव स्वीकृति दर",
  "prog.activity": "गतिविधि — पिछले 14 दिन", "prog.byLanguage": "भाषा के अनुसार गतिविधि", "prog.recentHistory": "हाल के सुधार", "prog.errorsByType": "प्रकार के अनुसार त्रुटियाँ",
  "prog.empty": "आपके अभी कोई सुधार नहीं हैं। कोच पृष्ठ पर जाएँ, एक वाक्य लिखें और “पाठ सुधारें” दबाएँ।", "prog.goCoach": "कोच खोलें", "prog.none": "—", "prog.original": "मूल", "prog.correctedText": "सुधारा हुआ (O2)",
};

const ja: Dict = {
  "nav.translate": "翻訳",
  "auth.name": "名前", "auth.identifier": "ユーザー名またはメールアドレス", "auth.confirm": "パスワード（確認）", "auth.role": "役割", "auth.prefLang": "使用言語",
  "auth.demoAs": "デモアカウント — クリックでサインイン（パスワード「demo」）", "auth.protoRole": "プロトタイプ：役割を自分で選択できます。自己登録した教育者は独立した検証として数えられません。",
  "auth.hint.identifier": "ユーザー名（3〜32文字の英数字とアンダースコア）またはメールアドレス",
  "err.name_required": "名前を入力してください。", "err.invalid_email": "有効なメールアドレスを入力してください。", "err.password_mismatch": "パスワードが一致しません。",
  "err.translation_unavailable": "現在翻訳を利用できません（モデルがない、またはプロバイダー未設定）。", "err.same_language": "異なる2つの言語を選んでください。", "err.required": "必須項目をすべて入力してください。", "err.model_unavailable": "サーバーで必要なモデルが利用できません。",
  "coach.sampleNext": "サンプルを挿入", "coach.textLangNote": "これは入力するテキストの言語です。表示言語は右上で選択します。",
  "tr.title": "翻訳", "tr.subtitle": "言語間の機械翻訳です。文法添削とは別の機能です。", "tr.source": "翻訳元", "tr.target": "翻訳先", "tr.input": "翻訳するテキスト",
  "tr.placeholder": "テキストを入力または貼り付けてください…", "tr.button": "翻訳", "tr.working": "翻訳中…（最初のリクエストはモデルを読み込みます）", "tr.output": "翻訳結果", "tr.swap": "言語を入れ替え",
  "tr.provider": "プロバイダー：{p} · モデル：{m}", "tr.license": "モデルのライセンス：{l}（非商用）。", "tr.note": "機械翻訳には誤りが含まれる場合があります。オディア語とテルグ語は低リソース言語のため精度が低めです。",
  "prog.corrections": "添削の総数", "prog.corrected": "修正された文", "prog.avgConf": "平均信頼度（未較正）", "prog.acceptRate": "提案の受け入れ率",
  "prog.activity": "アクティビティ — 過去14日間", "prog.byLanguage": "言語別アクティビティ", "prog.recentHistory": "最近の添削", "prog.errorsByType": "種類別の誤り",
  "prog.empty": "まだ添削がありません。コーチページで文を書いて「添削する」を押してください。", "prog.goCoach": "コーチを開く", "prog.none": "—", "prog.original": "元の文", "prog.correctedText": "添削後（O2）",
};

const ko: Dict = {
  "nav.translate": "번역",
  "auth.name": "이름", "auth.identifier": "사용자 이름 또는 이메일", "auth.confirm": "비밀번호 확인", "auth.role": "역할", "auth.prefLang": "선호 언어",
  "auth.demoAs": "데모 계정 — 클릭하여 로그인(비밀번호 “demo”)", "auth.protoRole": "프로토타입: 역할을 직접 선택할 수 있습니다. 직접 가입한 교육자는 독립적인 검증으로 집계되지 않습니다.",
  "auth.hint.identifier": "사용자 이름(3–32자의 영문, 숫자, 밑줄) 또는 이메일 주소",
  "err.name_required": "이름을 입력해 주세요.", "err.invalid_email": "올바른 이메일 주소를 입력해 주세요.", "err.password_mismatch": "비밀번호가 일치하지 않습니다.",
  "err.translation_unavailable": "지금은 번역을 사용할 수 없습니다(모델 없음 또는 제공자 미설정).", "err.same_language": "서로 다른 두 언어를 선택하세요.", "err.required": "필수 항목을 모두 입력해 주세요.", "err.model_unavailable": "서버에서 필요한 모델을 사용할 수 없습니다.",
  "coach.sampleNext": "예시 넣기", "coach.textLangNote": "작성하는 텍스트의 언어입니다. 인터페이스 언어는 오른쪽 위에서 선택하세요.",
  "tr.title": "번역", "tr.subtitle": "언어 간 기계 번역입니다. 문법 교정과는 별개의 기능입니다.", "tr.source": "원본 언어", "tr.target": "대상 언어", "tr.input": "번역할 텍스트",
  "tr.placeholder": "텍스트를 입력하거나 붙여넣으세요…", "tr.button": "번역", "tr.working": "번역 중… (첫 요청은 모델을 불러옵니다)", "tr.output": "번역 결과", "tr.swap": "언어 바꾸기",
  "tr.provider": "제공자: {p} · 모델: {m}", "tr.license": "모델 라이선스: {l}(비상업적).", "tr.note": "기계 번역에는 오류가 있을 수 있습니다. 오디아어와 텔루구어는 자원이 적은 언어라 정확도가 낮을 수 있습니다.",
  "prog.corrections": "전체 교정 수", "prog.corrected": "교정된 문장", "prog.avgConf": "평균 신뢰도(보정되지 않음)", "prog.acceptRate": "제안 수락률",
  "prog.activity": "활동 — 최근 14일", "prog.byLanguage": "언어별 활동", "prog.recentHistory": "최근 교정", "prog.errorsByType": "유형별 오류",
  "prog.empty": "아직 교정 기록이 없습니다. 코치 페이지에서 문장을 쓰고 “텍스트 교정”을 눌러 보세요.", "prog.goCoach": "코치 열기", "prog.none": "—", "prog.original": "원문", "prog.correctedText": "교정문(O2)",
};

export const EXTRA: Record<string, Dict> = { en, te, or, hi, ja, ko };
