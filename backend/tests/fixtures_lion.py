"""Acceptance-test story: "A lion cub makes a new friend in the forest", written
natively in English, Tamil, Telugu and Hindi (used as an LLM test double)."""
import json

IMAGE = [
    "golden lion cub waking up at sunrise in a misty forest den",
    "lion cub chasing a blue butterfly through ferns, far from the den",
    "lion cub looking up at tall trees, ears raised, curious",
    "small brown monkey hanging upside down from a branch, smiling at a lion cub below",
    "lion cub sitting proudly, mouth open as if talking, friendly expression",
    "shy little monkey hiding behind big green leaves, peeking out",
    "lion cub gently nudging a ripe mango towards the tree with his paw",
    "little monkey climbing down the tree trunk, laughing",
    "lion cub and monkey playing hide and seek in tall golden grass",
    "rain falling in the forest, lion cub and monkey sheltering under a huge tree",
    "bright rainbow over the forest, lion cub and monkey watching side by side",
    "sunset, lion cub and monkey waving goodbye at the edge of the forest",
]
CAMERA = ["slow push in", "tracking", "tilt up", "pull out", "static", "slow push in", "pan right", "tilt down",
          "tracking", "pull out", "pan left", "pull out"]
SFX = [["birds", "wind"], ["rustle leaves", "birds"], ["birds", "wind"], ["leaves", "birds"], ["cub growl"], ["rustle leaves"],
       ["rustle"], ["leaves", "birds"], ["rustle", "footsteps"], ["rain", "thunder"], ["birds", "water"], ["crickets", "night"]]

TEXT = {  # per scene: (narration, [(speaker, line)])
    "en": [
        ("The morning sun woke the forest. Little lion Veeran opened his eyes.", []),
        ("Chasing a butterfly, Veeran wandered far from his den.", []),
        ("Suddenly, a giggle came from high in the trees.", []),
        ("A little monkey hung upside down from a branch.", [("monkey", "Who are you?")]),
        ("", [("cub", "I'm Veeran! Do you want to play with me?")]),
        ("But Chinnu was scared of lions. He hid among the leaves.", []),
        ("Veeran gently rolled a mango towards him.", [("cub", "This is for you!")]),
        ("Chinnu laughed and climbed down.", []),
        ("Together they played hide and seek in the tall grass.", []),
        ("Suddenly it began to rain. They sheltered under a big tree.", []),
        ("When the rain stopped, a beautiful rainbow filled the sky.", []),
        ("", [("monkey", "Can we play again tomorrow?"), ("cub", "Of course! We'll always be friends!")]),
    ],
    "ta": [
        ("காலைச் சூரியன் காட்டை எழுப்பியது. குட்டிச் சிங்கம் வீரனும் கண் விழித்தான்.", []),
        ("ஒரு வண்ணத்துப்பூச்சியைத் துரத்தியபடி வீரன் குகையை விட்டு வெகுதூரம் வந்தான்.", []),
        ("திடீரென்று மரத்தின் மேலிருந்து ஒரு சிரிப்புச் சத்தம் கேட்டது.", []),
        ("கிளையில் தலைகீழாகத் தொங்கிக்கொண்டிருந்தது ஒரு குட்டிக் குரங்கு.", [("monkey", "நீ யாரு?")]),
        ("", [("cub", "நான் வீரன்! என்கூட விளையாட வர்றியா?")]),
        ("ஆனால் சின்னுவுக்குச் சிங்கம் என்றாலே பயம். அவன் இலைகளுக்குள் ஒளிந்துகொண்டான்.", []),
        ("வீரன் மெதுவாக ஒரு மாம்பழத்தை அவன் பக்கம் உருட்டிவிட்டான்.", [("cub", "இது உனக்குத்தான்!")]),
        ("சின்னு சிரித்துக்கொண்டே கீழே இறங்கி வந்தான்.", []),
        ("இருவரும் உயரமான புற்களுக்கு நடுவே கண்ணாமூச்சி விளையாடினார்கள்.", []),
        ("திடீரென்று மழை கொட்டியது. இருவரும் பெரிய மரத்தடியில் ஒதுங்கினார்கள்.", []),
        ("மழை நின்றதும் வானத்தில் அழகான வானவில் தோன்றியது.", []),
        ("", [("monkey", "நாளைக்கும் விளையாடலாமா?"), ("cub", "கண்டிப்பா! நாம எப்பவுமே நண்பர்கள்!")]),
    ],
    "te": [
        ("ఉదయపు సూర్యుడు అడవిని నిద్రలేపాడు. చిన్న సింహం వీరన్ కూడా కళ్ళు తెరిచాడు.", []),
        ("ఒక సీతాకోకచిలుక వెంట పరుగెడుతూ వీరన్ గుహకు చాలా దూరం వచ్చేశాడు.", []),
        ("అకస్మాత్తుగా చెట్టు పైనుంచి ఒక నవ్వు వినిపించింది.", []),
        ("కొమ్మకు తలకిందులుగా వేలాడుతోంది ఒక చిన్న కోతి.", [("monkey", "నువ్వెవరు?")]),
        ("", [("cub", "నేను వీరన్! నాతో ఆడుకుంటావా?")]),
        ("కానీ చిన్నుకి సింహమంటే భయం. అతను ఆకుల వెనక దాక్కున్నాడు.", []),
        ("వీరన్ మెల్లగా ఒక మామిడిపండును అతని వైపు దొర్లించాడు.", [("cub", "ఇది నీకోసమే!")]),
        ("చిన్ను నవ్వుతూ కిందకు దిగి వచ్చాడు.", []),
        ("ఇద్దరూ పొడవాటి గడ్డిలో దాగుడుమూతలు ఆడుకున్నారు.", []),
        ("ఉన్నట్టుండి వర్షం మొదలైంది. ఇద్దరూ పెద్ద చెట్టు కింద తలదాచుకున్నారు.", []),
        ("వర్షం ఆగగానే ఆకాశంలో అందమైన ఇంద్రధనుస్సు కనిపించింది.", []),
        ("", [("monkey", "రేపు కూడా ఆడుకుందామా?"), ("cub", "తప్పకుండా! మనం ఎప్పటికీ స్నేహితులం!")]),
    ],
    "hi": [
        ("सुबह के सूरज ने जंगल को जगाया। नन्हा शेर वीरन भी जाग गया।", []),
        ("एक तितली के पीछे भागते-भागते वीरन अपनी गुफ़ा से बहुत दूर आ गया।", []),
        ("अचानक पेड़ के ऊपर से किसी की हँसी सुनाई दी।", []),
        ("डाल पर उल्टा लटका था एक नन्हा बंदर।", [("monkey", "तुम कौन हो?")]),
        ("", [("cub", "मैं वीरन हूँ! मेरे साथ खेलोगे?")]),
        ("पर चिन्नू को शेरों से डर लगता था। वह पत्तों में छिप गया।", []),
        ("वीरन ने धीरे से एक आम उसकी तरफ़ लुढ़का दिया।", [("cub", "यह तुम्हारे लिए है!")]),
        ("चिन्नू हँसते हुए नीचे उतर आया।", []),
        ("दोनों ऊँची घास में लुका-छिपी खेलने लगे।", []),
        ("अचानक बारिश शुरू हो गई। दोनों बड़े पेड़ के नीचे छिप गए।", []),
        ("बारिश रुकी तो आसमान में सुंदर इंद्रधनुष निकल आया।", []),
        ("", [("monkey", "कल भी खेलेंगे?"), ("cub", "ज़रूर! हम हमेशा दोस्त रहेंगे!")]),
    ],
}
NAMES = {"en": ("Veeran", "Chinnu"), "ta": ("வீரன்", "சின்னு"), "te": ("వీరన్", "చిన్ను"), "hi": ("वीरन", "चिन्नू")}
TITLES = {"en": "Veeran's New Friend", "ta": "வீரனின் புதிய நண்பன்", "te": "వీరన్ కొత్త స్నేహితుడు", "hi": "वीरन का नया दोस्त"}


def story(lang: str, sub: str | None = None) -> dict:
    cub, monkey = NAMES[lang]
    scenes = []
    for i, (narr, lines) in enumerate(TEXT[lang]):
        sc = {"number": i + 1, "duration_s": 5, "description": IMAGE[i], "characters": ["cub", "monkey"] if i >= 3 else ["cub"],
              "environment": "lush tropical forest", "image_prompt": IMAGE[i], "video_prompt": IMAGE[i],
              "camera_movement": CAMERA[i], "camera_angle": "eye level", "lighting": "soft golden light", "emotions": "curious, warm",
              "narration": narr, "dialogue": [{"character": k, "line": l} for k, l in lines], "sfx": SFX[i],
              "music": "gentle playful strings", "transition": "dissolve" if i % 3 else "fade"}
        if sub:
            sn, sl = TEXT[sub][i]
            sc["narration_subtitle"] = sn
            for d, (_, line) in zip(sc["dialogue"], sl):
                d["subtitle"] = line
        scenes.append(sc)
    return {"title": TITLES[lang], "logline": "A lion cub makes a new friend in the forest.", "visual_style": "cinematic 3D animation",
            "music_theme": "playful, warm, hopeful friendship",
            "characters": [
                {"key": "cub", "name": "Veeran", "name_native": cub, "role": "protagonist", "species": "lion cub", "color": "golden fur",
                 "eye_color": "amber", "markings": "small dark tuft on the tail", "personality": "brave, kind, playful"},
                {"key": "monkey", "name": "Chinnu", "name_native": monkey, "role": "supporting", "species": "baby monkey",
                 "color": "light brown fur", "eye_color": "dark brown", "personality": "shy, funny"}],
            "scenes": scenes}


def as_json(lang: str, sub: str | None = None) -> str:
    return json.dumps(story(lang, sub), ensure_ascii=False)
