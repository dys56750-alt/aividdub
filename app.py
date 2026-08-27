import streamlit as st
import os
import re
import ssl
import subprocess
import glob
import shutil
import base64
import requests
import urllib3
from pydub import AudioSegment
import yt_dlp
from google import genai

# Setup SSL & Warnings
ssl._create_default_https_context = ssl._create_unverified_context
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="Khmer Dubbing Studio Pro", layout="wide")

# Custom UI Styling for Speed & Compact Elements
st.markdown("""
    <style>
    div[data-baseweb="input"] input {
        background-color: #121214 !important;
        color: #FFFFFF !important;
        font-size: 14px !important;
        border: 1px solid #333333 !important;
        padding: 6px 10px !important;
    }
    div[data-baseweb="select"] > div {
        background-color: #121214 !important;
        color: #FFFFFF !important;
        font-size: 13px !important;
        border: 1px solid #333333 !important;
        min-height: 38px !important;
    }
    div.stButton > button[kind="primary"] {
        background-color: #28a745 !important;
        border-color: #28a745 !important;
        color: white !important;
        font-weight: bold !important;
    }
    .time-header {
        color: #28a745;
        font-size: 14px;
        font-weight: bold;
        margin-top: 8px;
        margin-bottom: 2px;
    }
    </style>
""", unsafe_allow_html=True)

# File Paths
CACHE_SCRIPT_FILE = "cached_script.txt"
video_input_path = "original_video.mp4"
extracted_mp3_path = "extracted_audio.mp3"
raw_khmer_audio = "raw_khmer_audio.mp3"
final_video_no_sub = "final_dubbed_audio_only.mp4"

def get_dir_size_mb():
    total_size = 0
    for dirpath, dirnames, filenames in os.walk('.'):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    return total_size / (1024 * 1024)

def hard_reset_all():
    files_to_delete = [
        CACHE_SCRIPT_FILE, video_input_path, extracted_mp3_path, 
        raw_khmer_audio, final_video_no_sub,
        "temp_dl_video.mp4", "temp_dl_audio.mp3", "t_raw_vid.mp4", "t_raw_aud.mp3"
    ]
    for f in files_to_delete:
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass
            
    for pattern in ["*.mp3", "*.wav", "*.mp4", "*.srt", "*.ass"]:
        for f in glob.glob(pattern):
            try: os.remove(f)
            except Exception: pass

    for p in glob.glob("temp_*") + glob.glob("raw_*") + glob.glob("t_raw_*") + ["temp_processing", "__pycache__"]:
        if os.path.exists(p):
            try:
                if os.path.isdir(p): shutil.rmtree(p, ignore_errors=True)
                else: os.remove(p)
            except Exception: pass
            
    st.session_state.clear()

st.title("🎬 Khmer Dubbing Studio Pro")

col_info, col_reset = st.columns([2.5, 1.5])
with col_info:
    st.info("💡 ដំណើរការ៖ ១. បញ្ចូលវីដេអូ ➔ ២. Gemini 3.6 Pro បកប្រែ ➔ ៣. ផ្ទៀងផ្ទាត់ ➔ ៤. Auto-Sync & Render")
with col_reset:
    used_mb = get_dir_size_mb()
    st.metric(label="💾 Disk Usage", value=f"{used_mb:.1f} MB")
    if st.button("🗑️ Reset Storage", type="secondary", use_container_width=True):
        hard_reset_all()
        st.success("✅ បានសម្អាតទំហំផ្ទុកជោគជ័យ!")
        st.rerun()

st.divider()

# 1. API Key
st.subheader("🔑 ១. បញ្ចូល Gemini API Key")
gemini_key = st.text_input("🔑 Gemini API Key:", type="password", value="")

st.divider()

def get_video_duration_ms(file_path):
    try:
        chk = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True, text=True
        )
        return int(float(chk.stdout.strip()) * 1000)
    except Exception:
        return 0

def get_clean_tiktok_url(url):
    try:
        session = requests.Session()
        res = session.get(url, allow_redirects=True, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        return res.url.split('?')[0]
    except Exception:
        return url

def download_video_all(url, out_path):
    url = url.strip()
    for f in [out_path, "t_raw_vid.mp4", "t_raw_aud.mp3"]:
        if os.path.exists(f):
            try: os.remove(f)
            except Exception: pass

    # 1. TikTok
    if "tiktok.com" in url.lower() or "vt.tiktok" in url.lower():
        real_url = get_clean_tiktok_url(url)
        try:
            api_url = "https://www.tikwm.com/api/"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36',
                'Accept': 'application/json'
            }
            res = requests.post(api_url, headers=headers, data={'url': real_url, 'count': 12, 'cursor': 0, 'web': 1, 'hd': 1}, timeout=15).json()
            if res.get("code") == 0 and "data" in res:
                v_url = res["data"].get("hdplay") or res["data"].get("play") or res["data"].get("wmplay")
                if v_url:
                    if not v_url.startswith("http"):
                        v_url = "https://www.tikwm.com" + ("" if v_url.startswith("/") else "/") + v_url
                    rv = requests.get(v_url, headers={'User-Agent': 'Mozilla/5.0'}, verify=False, timeout=30)
                    with open(out_path, "wb") as f:
                        f.write(rv.content)
                    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                        return True, "ជោគជ័យតាម TikWM"
        except Exception:
            pass

        try:
            ss_res = requests.post(
                "https://ssstik.io/abc?url=dl",
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'},
                data={'id': real_url, 'locale': 'en', 'tt': 'none'},
                timeout=15
            ).text
            match = re.search(r'href="(https://[^"]+)" class="[^"]*download_link', ss_res)
            if match:
                dl_link = match.group(1)
                rv = requests.get(dl_link, headers={'User-Agent': 'Mozilla/5.0'}, verify=False, timeout=30)
                with open(out_path, "wb") as f:
                    f.write(rv.content)
                if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
                    return True, "ជោគជ័យតាម SSSTik"
        except Exception:
            pass

        return False, "មិនអាចទាញយក TikTok បានទេ!"

    # 2. YouTube / Others
    ydl_opts = {
        'format': 'best[ext=mp4]/bestvideo+bestaudio/best',
        'outtmpl': out_path,
        'nocheckcertificate': True,
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        },
        'extractor_args': {
            'youtube': {'player_client': ['android', 'ios', 'web']}
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
            return True, "ជោគជ័យ"
    except Exception as e:
        return False, f"កំហុសទាញយក៖ {e}"

    return False, "មិនអាចទាញយកបានទេ សូម Upload File MP4"

def generate_khmer_dub_srt_pro(audio_path: str, api_key: str) -> str:
    client = genai.Client(api_key=api_key)
    uploaded_audio = client.files.upload(file=audio_path)

    prompt = r"""
Listen to the audio and create a valid SRT for dubbing into Khmer.

Strict Rules:
1. Transcribe speech accurately and translate naturally into Khmer.
2. Accurately detect speaker gender for each subtitle line.
3. Every subtitle line MUST start with exactly one tag:
   (female) = for female voice
   (man) = for male voice
4. Return ONLY valid SRT format. Do not add markdown blocks (no ```srt), explanations, or notes.
5. Provide EVERY dialogue line until the very end of the file.

Example Format:
1
00:00:01,000 --> 00:00:03,500
(female) សួស្តី! តើអ្នកសុខសប្បាយទេ?

2
00:00:03,600 --> 00:00:05,200
(man) បាទ ខ្ញុំសុខសប្បាយទេ។
"""
    candidate_models = ["gemini-3.6-pro", "gemini-3.6-flash", "gemini-2.5-flash"]
    last_error = None

    for m_name in candidate_models:
        try:
            response = client.models.generate_content(
                model=m_name,
                contents=[prompt, uploaded_audio],
            )
            try: client.files.delete(name=uploaded_audio.name)
            except Exception: pass

            raw_text = getattr(response, "text", "").strip()
            cleaned_srt = re.sub(r"^\s*```(?:srt|text)?\s*", "", raw_text, flags=re.I)
            cleaned_srt = re.sub(r"\s*```\s*$", "", cleaned_srt).strip()
            return cleaned_srt
        except Exception as err:
            last_error = err
            continue

    try: client.files.delete(name=uploaded_audio.name)
    except Exception: pass
    raise last_error

def parse_time_to_ms(t):
    t = t.replace(',', '.').strip()
    p = t.split(':')
    if len(p) == 3: 
        return int((int(p[0]) * 3600 + int(p[1]) * 60 + float(p[2])) * 1000)
    elif len(p) == 2: 
        return int((int(p[0]) * 60 + float(p[1])) * 1000)
    elif len(p) == 1:
        return int(float(p[0]) * 1000)
    return 0

def clean_speech_text(text):
    patterns = [
        r'\[\s*(ស្រី|female|woman|girl|f)\s*\]:?',
        r'\(\s*(ស្រី|female|woman|girl|f)\s*\):?',
        r'\[\s*(ប្រុស|male|man|boy|m)\s*\]:?',
        r'\(\s*(ប្រុស|male|man|boy|m)\s*\):?',
        r'^(ស្រី|female|woman|girl|f)\s*[:：\-]\s*',
        r'^(ប្រុស|male|man|boy|m)\s*[:：\-]\s*'
    ]
    cleaned = text
    for pat in patterns:
        cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r'\s+\d{1,4}$', '', cleaned).strip()
    return re.sub(r'^[\[\(].*?[\]\)]\s*[:：]?', '', cleaned).strip()

def parse_srt_to_list(srt_text):
    if not srt_text.strip():
        return []
    pattern = re.compile(
        r'(?:(\d+)\s*\n)?'
        r'((?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3})\s*-->\s*((?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3})'
        r'[\r\n]+([\s\S]*?)(?=(?:\r?\n\s*\d+\s*\r?\n(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3})|(?:\r?\n\s*(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{1,3}\s*-->)|$)',
        re.MULTILINE
    )
    
    items = []
    for match in pattern.finditer(srt_text):
        seq, start_t, end_t, text_block = match.groups()
        full_txt = " ".join([l.strip() for l in text_block.strip().splitlines() if l.strip()])
        if not full_txt:
            continue
            
        tag = "(female)" if any(k in full_txt.lower() for k in ["female", "ស្រី", "(f)", "[ស្រី]"]) else "(man)"
        cleaned_text = clean_speech_text(full_txt)
        
        items.append({
            "seq": seq or str(len(items) + 1),
            "start_raw": start_t.replace('.', ','),
            "end_raw": end_t.replace('.', ','),
            "start": parse_time_to_ms(start_t),
            "end": parse_time_to_ms(end_t),
            "tag": tag,
            "text": cleaned_text
        })
    return items

def generate_and_fit_audio(text, voice, out_path, target_ms):
    temp_raw = f"raw_{out_path}"
    subprocess.run(["edge-tts", "--voice", voice, "--text", text, "--write-media", temp_raw], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    if os.path.exists(temp_raw):
        seg = AudioSegment.from_file(temp_raw)
        actual_ms = len(seg)
        if target_ms <= 0:
            target_ms = actual_ms
        
        factor = actual_ms / target_ms
        if factor > 1.25:
            factor = min(1.4, factor)
            subprocess.run(["ffmpeg", "-y", "-i", temp_raw, "-filter:a", f"atempo={factor:.2f}", out_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            if os.path.exists(temp_raw): os.remove(temp_raw)
        else:
            if os.path.exists(out_path): os.remove(out_path)
            os.rename(temp_raw, out_path)

def process_gemini_translation(api_key, status_container):
    status_container.info("⏳ ជំហានទី ១/២៖ កំពុងបន្សុទ្ធសំឡេង (16kHz Mono)...")
    subprocess.run([
        "ffmpeg", "-y", "-i", video_input_path,
        "-vn", "-ar", "16000", "-ac", "1", "-b:a", "128k",
        extracted_mp3_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    if not os.path.exists(extracted_mp3_path) or os.path.getsize(extracted_mp3_path) < 1000:
        status_container.error("❌ មិនអាចទាញយកសំឡេងពីវីដេអូបានទេ!")
        return False
    
    try:
        status_container.info("✨ ជំហានទី ២/២៖ Gemini 3.6 Pro កំពុងស្ដាប់ & បកប្រែជាភាសាខ្មែរ...")
        srt_output = generate_khmer_dub_srt_pro(extracted_mp3_path, api_key)
        with open(CACHE_SCRIPT_FILE, "w", encoding="utf-8") as f: 
            f.write(srt_output)
        status_container.success("🎉 Gemini 3.6 Pro បានបកប្រែរួចរាល់ពេញលេញ!")
        return True
    except Exception as e:
        status_container.error(f"❌ កំហុស Gemini ({e})។ វីដេអូបានរក្សាទុកលើ Server រួចហើយ សូមចុចប៊ូតុង Retry ខាងក្រោមដើម្បីសាកល្បងម្ដងទៀត។")
        return False

# 2. Video Source
st.subheader("📥 ២. ប្រភពវីដេអូដើម")
input_opt = st.radio("វិធីសាស្ត្របញ្ចូលវីដេអូ៖", ["🔗 URL Link (TikTok/Dailymotion/FB/YouTube)", "📂 Upload File MP4"], key="v_opt")

if input_opt == "🔗 URL Link (TikTok/Dailymotion/FB/YouTube)":
    url_in = st.text_input("🔗 បញ្ចូល Link វីដេអូ៖", placeholder="https://vt.tiktok.com/... ឬ https://youtube.com/...")
    if st.button("📥 ទាញយក & អូតូបកប្រែជាមួយ Gemini 3.6 Pro", type="secondary"):
        if not url_in.strip(): 
            st.error("សូមបញ្ចូល URL!")
        elif not gemini_key.strip():
            st.error("❌ សូមបញ្ចូល Gemini API Key នៅជំហានទី ១ ជាមុនសិន!")
        else:
            if os.path.exists(CACHE_SCRIPT_FILE): os.remove(CACHE_SCRIPT_FILE)
            st_box = st.empty()
            st_box.info("⏳ កំពុងទាញយកវីដេអូចូល Server...")
            ok, msg = download_video_all(url_in.strip(), video_input_path)
            if ok:
                st.toast("🎉 ទាញយកវីដេអូចូល Server ជោគជ័យ!", icon="✅")
                st_box.success("✅ ទាញយកវីដេអូជោគជ័យ! កំពុងចាប់ផ្ដើមបកប្រែ...")
                process_gemini_translation(gemini_key.strip(), st_box)
                st.rerun()
            else: 
                st.toast(f"❌ បរាជ័យក្នុងការទាញយក៖ {msg}", icon="🚨")
                st_box.error(f"❌ {msg}")
else:
    up_v = st.file_uploader("📂 Upload File MP4 វីដេអូដើម", type=["mp4", "mov"])
    if up_v:
        if not gemini_key.strip():
            st.warning("⚠️ សូមបញ្ចូល Gemini API Key នៅជំហានទី ១ ដើម្បីឱ្យវាបកប្រែស្វ័យប្រវត្តិ។")
        if not os.path.exists(video_input_path) or os.path.getsize(video_input_path) != up_v.size:
            with open(video_input_path, "wb") as f: f.write(up_v.read())
            st.toast("✅ បាន Upload វីដេអូជោគជ័យ!", icon="🎉")
            if gemini_key.strip():
                st_box_up = st.empty()
                process_gemini_translation(gemini_key.strip(), st_box_up)
                st.rerun()

st.divider()

# 3. Fast Video Player + Subtitle Editor
st.subheader("📝 ៣. ផ្ទៀងផ្ទាត់ & កែសម្រួល Script SRT")

if st.session_state.get("just_saved", False):
    st.success("✅ បានរក្សាទុកការកែប្រែ Script SRT ជោគជ័យ ១០០%!")
    st.session_state["just_saved"] = False

# Fast Native Video Player
if os.path.exists(video_input_path):
    st.video(video_input_path)

cur_script = open(CACHE_SCRIPT_FILE, 'r', encoding='utf-8').read() if os.path.exists(CACHE_SCRIPT_FILE) else ""
sub_list = parse_srt_to_list(cur_script)

# Retry Button
if os.path.exists(video_input_path) and not sub_list:
    st.warning("⚠️ វីដេអូមានលើ Server រួចហើយ ប៉ុន្តែមិនទាន់មាន Script SRT (អាចបណ្ដាលមកពី Gemini Server 503)។")
    if st.button("🔄 សាកល្បងបកប្រែម្ដងទៀតជាមួយ Gemini 3.6 Pro (Retry)", type="primary", use_container_width=True):
        if not gemini_key.strip():
            st.error("❌ សូមបញ្ចូល Gemini API Key ជាមុនសិន!")
        else:
            retry_box = st.empty()
            if process_gemini_translation(gemini_key.strip(), retry_box):
                st.rerun()

def save_current_subtitles(items_data):
    reconstructed_srt = []
    for i, item in enumerate(items_data):
        tag_val = st.session_state.get(f"tag_{i}", item["tag"])
        txt_val = st.session_state.get(f"txt_{i}", item["text"])
        reconstructed_srt.append(f"{i+1}\n{item['start_raw']} --> {item['end_raw']}\n{tag_val} {txt_val}\n")
    
    final_saved_srt = "\n".join(reconstructed_srt)
    with open(CACHE_SCRIPT_FILE, "w", encoding="utf-8") as f:
        f.write(final_saved_srt)
    st.session_state["just_saved"] = True
    st.toast("✅ បានរក្សាទុកការកែប្រែ Script ជោគជ័យ!", icon="💾")

if sub_list:
    st.markdown(f"#### 📋 រកឃើញសរុប **{len(sub_list)} ជួរ**")
    
    # Save button Top
    if st.button("💾 រក្សាទុកការកែប្រែ Script (Save Top)", type="primary", key="btn_save_top", use_container_width=True):
        save_current_subtitles(sub_list)
        st.rerun()

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

    for i, item in enumerate(sub_list):
        st.markdown(f"""
            <div class="time-header">
                #{i+1} [{item['start_raw']} ➔ {item['end_raw']}]
            </div>
        """, unsafe_allow_html=True)
        
        c_tag, c_txt = st.columns([0.8, 4.2])
        with c_tag:
            st.selectbox(
                f"Tag #{i+1}",
                options=["(man)", "(female)"],
                format_func=lambda x: "👨 ប្រុស" if x == "(man)" else "👩 ស្រី",
                index=0 if item["tag"] == "(man)" else 1,
                key=f"tag_{i}",
                label_visibility="collapsed"
            )
        with c_txt:
            st.text_input(
                f"Text #{i+1}",
                value=item["text"],
                key=f"txt_{i}",
                label_visibility="collapsed"
            )
        st.markdown("<hr style='margin: 6px 0; border:0; border-top: 1px solid #222;'>", unsafe_allow_html=True)

    # Save button Bottom
    if st.button("💾 រក្សាទុកការកែប្រែ Script (Save Bottom)", type="primary", key="btn_save_bottom", use_container_width=True):
        save_current_subtitles(sub_list)
        st.rerun()
elif not os.path.exists(video_input_path):
    st.info("💡 សូមបញ្ចូល Link ឬ Upload វីដេអូដើម្បីឱ្យប្រព័ន្ធទាញយក និងបកប្រែស្វ័យប្រវត្តិ។")

st.divider()

v_choice = st.selectbox("🎙️ សំឡេងអាន៖", ["🤖 អូតូ (ប្រុស/ស្រី តាម Tag)", "👨 Piseth (ប្រុសសុទ្ធ)", "👩 Sreymom (ស្រីសុទ្ធ)"])

st.divider()

# 4. Auto-Sync & Auto-Render Final Video
st.subheader("🔊 ៤. បង្កើតសំឡេង Auto-Sync & Auto-Render វីដេអូ")

if st.button("🚀 ចាប់ផ្ដើមបង្កើតសំឡេង Auto-Sync & Auto-Render វីដេអូ", type="primary", use_container_width=True):
    fresh_script = open(CACHE_SCRIPT_FILE, 'r', encoding='utf-8').read() if os.path.exists(CACHE_SCRIPT_FILE) else ""
    if not fresh_script.strip(): 
        st.error("សូមបញ្ចូល Script SRT!")
    elif not os.path.exists(video_input_path):
        st.error("❌ មិនទាន់មានវីដេអូដើមទេ!")
    else:
        parsed_items = parse_srt_to_list(fresh_script)
        total = len(parsed_items)
        st.markdown(f"### 📊 រកឃើញសរុប **{total} ជួរ**")
        
        if total > 0:
            vid_dur_ms = get_video_duration_ms(video_input_path)
            max_item_end = max(it["end"] for it in parsed_items)
            total_duration_ms = max(vid_dur_ms, max_item_end + 1000)
            
            combined = AudioSegment.silent(duration=total_duration_ms)
            
            prog = st.progress(0)
            status = st.empty()
            
            for idx, it in enumerate(parsed_items):
                status.text(f"⚡ កំពុង Sync ជួរទី {idx+1}/{total}: {it['text'][:25]}...")
                
                v = "km-KH-PisethNeural"
                if "🤖" in v_choice or "អូតូ" in v_choice:
                    if it["tag"] == "(female)":
                        v = "km-KH-SreymomNeural"
                elif "👩" in v_choice:
                    v = "km-KH-SreymomNeural"

                temp_f = f"temp_{idx}.mp3"
                target_duration = it["end"] - it["start"]
                try:
                    generate_and_fit_audio(it["text"], v, temp_f, target_duration)
                    if os.path.exists(temp_f):
                        seg = AudioSegment.from_file(temp_f)
                        combined = combined.overlay(seg, position=it["start"])
                        os.remove(temp_f)
                except Exception: 
                    pass
                prog.progress(int((idx + 1) / total * 100))
                
            if vid_dur_ms > 0 and len(combined) > vid_dur_ms:
                combined = combined[:vid_dur_ms]
            elif vid_dur_ms > 0 and len(combined) < vid_dur_ms:
                combined += AudioSegment.silent(duration=(vid_dur_ms - len(combined)))

            combined.export(raw_khmer_audio, format="mp3")
            
            # Auto-Render វីដេអូ Dubbed
            status.text("⏳ កំពុង Auto-Render វីដេអូ Dubbed ជាមួយសំឡេងខ្មែរ...")
            ffmpeg_cmd = [
                "ffmpeg", "-y",
                "-i", video_input_path,
                "-i", raw_khmer_audio,
                "-c:v", "copy",
                "-c:a", "aac",
                "-map", "0:v:0",
                "-map", "1:a:0",
                final_video_no_sub
            ]
            subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            
            status.success(f"🎉 បង្កើតសំឡេង Auto-Sync និង Auto-Render វីដេអូពេញលេញរួចរាល់!")
            st.rerun()
        else:
            st.error("❌ មិនអាច Parse SRT បានទេ! សូមពិនិត្យមើលទម្រង់ម៉ោង។")

# Final Video Output
if os.path.exists(final_video_no_sub):
    st.markdown("#### 🎬 វីដេអូបញ្ចូលសំឡេងខ្មែររួចរាល់ (Dubbed Video Final)")
    st.video(final_video_no_sub)
    with open(final_video_no_sub, "rb") as vf1:
        st.download_button("📥 Download Dubbed Video Final (.mp4)", vf1, file_name="dubbed_video_final.mp4", type="primary", use_container_width=True)

st.divider()

# Audio Only Output
if os.path.exists(raw_khmer_audio):
    st.markdown("#### 🎵 សំឡេងអានខ្មែរ Auto-Sync សុទ្ធ (MP3 Audio Only)")
    st.audio(raw_khmer_audio, format="audio/mp3")
    with open(raw_khmer_audio, "rb") as af:
        st.download_button("📥 ទាញយក File MP3 សុទ្ធ (.mp3)", af, file_name="khmer_audio_synced.mp3", use_container_width=True)
                                           
