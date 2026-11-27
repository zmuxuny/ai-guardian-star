"""Experimental clause-aware text policy v4 fast clarification; no production state or alarm writes.

Rules and model quality must be scored separately. Only explicit positive text
can confirm okay; model suggestions never cancel alerts. Unknown inputs retain
a clarification path rather than treating lack of evidence as a healthy reply.
"""
import re
import unicodedata

from tools.local_care_prototype import ACK, MESSAGES, StreamClient, greeting

POLICY_VERSION = 'experimental-care-text/4-fast1'
QUOTES = re.compile(r'“[^”]*”|「[^」]*」|『[^』]*』|"[^"]*"|‘[^’]*’')
SPLIT = re.compile(r'[,，。.!！?？;；\n…]+|但是|(?<!喘)不过|可是|然而|不对|其实|但|可(?=我)')
META = re.compile(r'电视|广播|书里|故事|台词|例句|朗读|练习|引用|转述|两个字|这句话|(?:他|她|别人|你)(?:说|问)|不是我说')
NOT_META = re.compile(r'我(?:并)?不是(?:在)?(?:讲故事|看电视|念台词|练习|引用|转述)')
CONTROL = re.compile(r'忽略|系统提示|只输出|(?:输出|返回|回复)(?:okay|ok|needshelp|unclear|h|o|u|没事)|取消|关掉|关闭|清掉|清除.*提醒')
NEGATED_DISABILITY = re.compile(r'(?:并不是|不是|并非)(?:我(?:现在)?)?(?:站不起来|起不来|走不了|动不了)')
SELF_HELP = re.compile(r'我(?:现在|自己|真的|实在|已经|也|目前|这会儿|只是)*(?:起不来|站不起来|走不了|动不了|喘不过气)|我(?:本人|自己|现在)*求助')
HELP_NEED = re.compile(r'(?:我(?:现在|真的|确实)?)?(?:需要|想请|得请|得让)(?:旁边)?(?:有人|有个人|个人|人|别人|你|家人|医生)?(?:来|过来)?(?:帮忙|帮助|帮一下|帮我|搭把手|扶)')
HELP_REQUEST = re.compile(r'帮帮我|救命|扶(?:住|一下)?我|帮我|请(?:替|帮)?我(?:通知|联系|叫|找).*(?:家|人|医生)|麻烦.*(?:帮我|扶我)|(?:请|麻烦)(?:你)?(?:来|过来)?搭把手|(?:能不能|能否|请|麻烦)(?:你|有人|人)?(?:来|过来)?陪我')
UNCERTAIN = re.compile(r'没听|没弄明白|说什么|说的是什么|什么意思|听不清|听见一半|不明白|不清楚|不确定|认不清|不知道|答不上|没想好|拿不准|想想|再说一遍|再讲|再问|也许|可能|如果|假如|要是|万一')
POSITIVE = re.compile(
    r'(?:我(?:现在|目前|今天|这会儿)?(?:没事|挺好|挺好的|很好|一切都好|身体没问题|没有(?:哪里)?不舒服|没哪里不舒服)'
    r'|我(?:现在|目前|这边|已经|自己)*(?:能|可以)(?:自己|正常)*(?:站起来|走|走路|走动|起身(?:活动)?|处理|活动|安排好)'
    r'|我(?:这边|已经|自己)*(?:处理好了|解决好了|收拾妥了)|一切都好|身体没问题|精神不错|人好好的'
    r'|(?:暂时|也)?(?:不需要|不用|不必|无需)(?:你|人|家人)?(?:帮助|帮忙|帮我|协助|人来|过来|找医生|叫家人|找人陪着)'
    r'|不用麻烦(?:家里人|家人)|不是(?:我|身体)?不舒服|(?:我)?没有(?:碰到|遇到)?(?:困难|问题|求助)'
    r'|只是坐着休息)(?:了|的|呢|谢谢关心)?$')
CARE_CUE = re.compile(r'我|身体|身上|帮|扶|需要|感觉|不适|不舒服|难受|家人|医生')
WEAK_ASSISTANCE = re.compile(r'请人|来看看我|陪我|陪着我|想找人|想让人|找谁.*帮')
NEGATION_PREFIX = re.compile(r'(?:并非|不是|没有|不想|不愿意|不打算|不希望|不必|不用|不要|无需|没让|不让|不需要|没喊|不喊|没叫|不叫|别|不)(?:让|请|找|叫|需要|想|要|打算|希望|愿意|你|我|他|她|人|有人|来|过来|再|现在|真的|在|快)*$')
QUALIFIER_PREFIX = re.compile(r'也许|可能|不确定|如果|假如|要是|万一')
IMPERATIVE_PREFIX = re.compile(r'(?:快来|请来|请你|麻烦|现在请|赶紧来)$')
NEUTRAL = re.compile(
    r'(?:谢谢(?:关心|提醒|惦记)?|请放心(?:去忙)?|别担心|放心吧|不用担心'
    r'|(?:我)?(?:只是|刚才|刚刚|刚|方才|正在|在|是在)?(?:坐着|休息|坐着休息|看书|等水(?:烧)?开|伸了个懒腰|伸个懒腰)(?:一会儿|一会|片刻|一下|了一会儿|了一会|而已|了)?'
    r'|(?:我)?(?:刚|刚才|刚刚)?在(?:阳台|客厅|房里|屋里|椅子上)(?:坐|坐了|休息)(?:一会儿|一会|片刻)(?:了)?'
    r'|(?:今天|早上)?(?:起得晚(?:了点)?|多躺了片刻|睡晚了一点)(?:而已)?'
    r'|(?:我)?(?:只是)?伸手(?:取|拿)(?:杯子|东西))$')


DENIED_STATEMENT = re.compile(r'(?:没有|没|不是|并非|不曾|未曾)(?:在)?(?:说|表示|提出|要求|请求)(?:过)?(?:我|自己|本人|你|有人|人|家人|医生|别人|旁边|有个人|个人|现在|目前|需要|想请|想|要|找|让|请|叫|来|过来)*$')


# Whole-clause grammar only: unknown remainders must keep their original path.
DENIED_CLAUSE = re.compile(
    r'^(?:我)?(?:并)?(?:没有|没|不是|并非|不曾|未曾)(?:在)?(?:说|表示|提出|要求|请求)(?:过)?'
    r'(?:我|自己|本人)?(?:现在|目前)?(?:需要|想请|想找|想让|要|让|请)?(?:旁边)?'
    r'(?:有人|有个人|个人|人|别人|你|家人|医生)?(?:来|过来)?'
    r'(?:帮忙|帮助|帮一下|帮我(?:拿东西|联系家人|收拾)?|搭把手|扶我|陪我|陪着我|来看看我'
    r'|起不来|站不起来|动不了|走不了|喘不过气)(?:了|呢|一会儿|片刻)?$')


def _affirmed(pattern, clause):
    """Negation qualifies its matched action, not every other action in a clause."""
    for match in pattern.finditer(clause):
        prefix = clause[max(0, match.start() - 14):match.start()]
        if NEGATION_PREFIX.search(prefix) or DENIED_STATEMENT.search(prefix):
            continue
        if QUALIFIER_PREFIX.search(prefix) and not IMPERATIVE_PREFIX.search(prefix):
            continue
        return True
    return False


def _clean(text):
    return re.sub(r'[\W_]+', '', text).casefold()


def rule_intent(text):
    """Return a bounded rule decision or defer to a corroborated model advisory."""
    if not isinstance(text, str) or not text.strip():
        return 'unclear', 'empty'
    if len(text) > 300:
        return 'unclear', 'too_long'
    normalized = unicodedata.normalize('NFKC', text)
    unquoted = QUOTES.sub(' ', normalized)
    question = '?' in unquoted or '？' in unquoted
    clauses = []
    polite_conditions = {'假如能行', '如果可以', '如果方便', '要是方便', '若方便', '有空的话'}
    blocked = False
    conditional_scope = conditional_seen = False
    for fragment in SPLIT.split(unquoted):
        clause = _clean(fragment)
        clause = NOT_META.sub('', clause)
        if clause in polite_conditions:
            continue
        if not clause:
            continue
        if META.search(clause) or CONTROL.search(clause):
            blocked = True
            continue
        # A future/event condition scopes a following request too. Only an
        # explicit switch to the speaker's present state releases that scope.
        if re.search(r'如果|假如|要是|万一|^若', clause):
            conditional_scope = conditional_seen = True
        elif conditional_scope and re.search(r'我(?:现在|目前|这会儿)|(?:现在|目前|这会儿)我', clause):
            conditional_scope = False
        if conditional_scope:
            continue
        clause = NEGATED_DISABILITY.sub('', clause)
        if clause:
            clauses.append(clause)
    denied = [clause for clause in clauses if DENIED_CLAUSE.fullmatch(clause)]
    if denied and all(DENIED_CLAUSE.fullmatch(clause) or NEUTRAL.fullmatch(clause) for clause in clauses):
        return 'unclear', 'complete_denial_clarification'
    for clause in clauses:
        if _affirmed(SELF_HELP, clause) or _affirmed(HELP_NEED, clause) or _affirmed(HELP_REQUEST, clause):
            return 'needs_help', 'explicit_current_help'
    if conditional_seen or any(UNCERTAIN.search(clause) for clause in clauses) or question:
        return 'unclear', 'question_or_uncertainty'
    positives = [clause for clause in clauses if POSITIVE.fullmatch(clause)]
    if positives:
        remaining = [clause for clause in clauses if clause not in positives]
        if any(not NEUTRAL.fullmatch(clause) for clause in remaining):
            return 'unclear', 'positive_with_unresolved_clause'
        return 'okay', 'explicit_positive_clauses'
    if blocked or not clauses:
        return 'unclear', 'quoted_or_control_only'
    if not CARE_CUE.search(''.join(clauses)):
        return 'unclear', 'no_current_care_reply'
    return None, 'model_advisory_required'


def classify_reply(text, infer, *, emit=None):
    if emit is not None:
        emit({'kind': 'acknowledgement', 'text': ACK})
    intent, reason = rule_intent(text)
    result = {'policy_version': POLICY_VERSION, 'source': 'rule', 'intent': intent,
              'model_called': False, 'model_intent': None, 'auto_cancel': False,
              'preserve_alert': True, 'fallback_reason': reason}
    if intent is None:
        result['model_called'] = True
        try:
            prediction = infer(text)
            proposed = prediction['intent']
            if proposed not in MESSAGES:
                raise ValueError('invalid intent')
            result['model_intent'] = proposed
            # A vague symptom alone is not an explicit request. Keep a fixed
            # clarification unless the advisory has independent assistance cues.
            evidence = _clean(QUOTES.sub(' ', unicodedata.normalize('NFKC', text)))
            supported_help = proposed == 'needs_help' and _affirmed(WEAK_ASSISTANCE, evidence)
            result.update(intent='needs_help' if supported_help else 'unclear', source='model_advisory',
                          fallback_reason=None if supported_help else 'model_requires_confirmation')
        except Exception as error:
            result.update(intent='unclear', source='fallback', fallback_reason=type(error).__name__)
    result['message'] = MESSAGES[result['intent']]
    result['clarification_needed'] = result['intent'] == 'unclear'
    return result


class SemanticIntentClient(StreamClient):
    """Keep the established semantic JSON format with a five-second default."""
    def classify(self, text, *, timeout=5):
        return super().classify(text, timeout=timeout)
