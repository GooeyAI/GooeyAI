// The /new page's prompt box (AskGooeyNew in gooey-gui/app/components), for pages
// outside the app such as the Webflow home page, whose hero brings its own heading.
// Sending opens /new/?q=<prompt> on the app, which signs the visitor in if needed and
// starts a builder conversation with the prompt.
//
//   <div data-ask-gooey></div>
//   <script src="https://gooey.ai/static/js/ask_gooey_embed.js?v=1" defer><\/script>
//
// or paste this whole file between script tags in place of the src. (The closing tag
// above is escaped because a literal one would end such an inline script.) The div
// takes an optional data-placeholder.
//
// The markup and styles are AskGooeyNew's, as /new renders them, kept in a shadow
// root so the host page's CSS can't reach them. Keep the two in step. It sits on a
// transparent background, so the host page's shows through.
(() => {
  // the app is wherever this script is served from, so a staging copy sends visitors
  // to staging; pasted inline there is no src, and it falls back to production
  const NEW_PAGE_URL = new URL(
    "/new/",
    document.currentScript?.src || "https://gooey.ai"
  ).href;
  // the prompt rides in /new's url, and signing in nests that whole url, escaped again,
  // in ?next= - so a long prompt is cut to stay well inside request header limits
  const MAX_ENCODED_PROMPT_LENGTH = 4000;
  const GLOBAL_STYLE_ID = "ask-gooey-embed-global";
  // the heading /new shows above the box, kept as the box's accessible name
  const INPUT_LABEL = "What will you build today?";
  const DEFAULT_PLACEHOLDER = "Build an agent for farmers in Kenya";
  const SUGGESTION_CHARACTER_LIMIT = 38;
  const SUGGESTIONS = [
    "Swahili WhatsApp bot for community health workers",
    "Which AI models best understand Hausa?",
    "Eval models using google sheet of audio samples",
  ];
  // Font Awesome's glyphs as svg, so the host page needn't load Gooey's kit. The solid
  // ones are Font Awesome Free 6 (CC BY 4.0, https://fontawesome.com/license/free); the
  // regular ones are Pro there, so they are drawn here on the same grid.
  const ICONS = {
    plus: {
      width: 448,
      svg: '<path d="M224 72v368M40 256h368" fill="none" stroke="currentColor" stroke-width="48" stroke-linecap="round"/>',
    },
    microphone: {
      width: 384,
      svg: '<g fill="none" stroke="currentColor" stroke-width="48" stroke-linecap="round"><rect x="120" y="24" width="144" height="304" rx="72"/><path d="M40 216v40a152 152 0 0 0 304 0v-40M192 408v80M120 488h144"/></g>',
    },
    microphoneRecording: {
      width: 384,
      className: "fa-beat-fade",
      svg: '<path d="M192 0C139 0 96 43 96 96l0 160c0 53 43 96 96 96s96-43 96-96l0-160c0-53-43-96-96-96zM64 216c0-13.3-10.7-24-24-24s-24 10.7-24 24l0 40c0 89.1 66.2 162.7 152 174.4l0 33.6-48 0c-13.3 0-24 10.7-24 24s10.7 24 24 24l72 0 72 0c13.3 0 24-10.7 24-24s-10.7-24-24-24l-48 0 0-33.6c85.8-11.7 152-85.3 152-174.4l0-40c0-13.3-10.7-24-24-24s-24 10.7-24 24l0 40c0 70.7-57.3 128-128 128s-128-57.3-128-128l0-40z"/>',
    },
    spinner: {
      width: 512,
      className: "fa-spin",
      svg: '<path d="M256 24a232 232 0 0 1 200.92 348" fill="none" stroke="currentColor" stroke-width="48" stroke-linecap="round"/>',
    },
    arrowUp: {
      width: 384,
      svg: '<path d="M214.6 41.4c-12.5-12.5-32.8-12.5-45.3 0l-160 160c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0L160 141.2 160 448c0 17.7 14.3 32 32 32s32-14.3 32-32l0-306.7L329.4 246.6c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3l-160-160z"/>',
    },
    chevronLeft: {
      width: 320,
      svg: '<path d="M9.4 233.4c-12.5 12.5-12.5 32.8 0 45.3l192 192c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3L77.3 256 246.6 86.6c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0l-192 192z"/>',
    },
    chevronRight: {
      width: 320,
      svg: '<path d="M310.6 233.4c12.5 12.5 12.5 32.8 0 45.3l-192 192c-12.5 12.5-32.8 12.5-45.3 0s-12.5-32.8 0-45.3L242.7 256 73.4 86.6c-12.5-12.5-12.5-32.8 0-45.3s32.8-12.5 45.3 0l192 192z"/>',
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountAll);
  } else {
    mountAll();
  }

  function mountAll() {
    if (!document.getElementById(GLOBAL_STYLE_ID)) {
      const style = document.createElement("style");
      style.id = GLOBAL_STYLE_ID;
      style.textContent = globalCss();
      document.head.appendChild(style);
    }
    for (const host of document.querySelectorAll("[data-ask-gooey]")) {
      mountAskGooey(host);
    }
  }

  function mountAskGooey(host) {
    // a second copy of this script on the page finds the widget already there
    if (host.shadowRoot) return;
    const placeholder = host.dataset.placeholder ?? DEFAULT_PLACEHOLDER;

    const root = host.attachShadow({ mode: "open" });
    root.innerHTML = `<style>${widgetCss()}</style>${widgetHtml()}`;
    const inputBar = root.querySelector(".ask-gooey-input-bar");
    const textarea = root.querySelector(".ask-gooey-textarea");
    const errorBox = root.querySelector(".ask-gooey-error");
    const suggestions = root.querySelector(".ask-gooey-suggestions");
    const scrollContainer = root.querySelector(".ask-gooey-suggestions-scroll");
    const fadeLeft = root.querySelector(".ask-gooey-suggestions-fade--left");
    const fadeRight = root.querySelector(".ask-gooey-suggestions-fade--right");
    const attachButton = root.querySelector(".ask-gooey-attach-btn");
    const micButton = root.querySelector(".ask-gooey-mic-btn");
    const sendButton = root.querySelector(".ask-gooey-send-btn");

    textarea.placeholder = placeholder;
    textarea.setAttribute("aria-label", INPUT_LABEL);
    for (const prompt of SUGGESTIONS) {
      const chip = document.createElement("button");
      chip.type = "button";
      chip.className = "ask-gooey-suggestion-chip";
      chip.textContent = truncateSuggestion(prompt);
      chip.addEventListener("click", () => setValue(prompt));
      scrollContainer.append(chip);
    }

    let isFocused = false;
    let isSubmitting = false;
    let micState = "idle";
    let error = null;
    const dictation = createDictation({
      getValue: () => textarea.value,
      setValue,
      setMicState(state) {
        micState = state;
        render();
      },
      setError(message) {
        error = message;
        render();
      },
    });
    micButton.hidden = !dictation;

    textarea.addEventListener("input", onValueChange);
    textarea.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        submit();
      }
    });
    textarea.addEventListener("focus", () => {
      isFocused = true;
      render();
    });
    textarea.addEventListener("blur", () => {
      isFocused = false;
      render();
    });
    fadeLeft.firstElementChild.addEventListener("click", () =>
      scrollContainer.scrollBy({ left: -250, behavior: "smooth" })
    );
    fadeRight.firstElementChild.addEventListener("click", () =>
      scrollContainer.scrollBy({ left: 250, behavior: "smooth" })
    );
    scrollContainer.addEventListener("scroll", checkScroll);
    // watching the chips too catches them widening once the webfont loads
    const resizeObserver = new ResizeObserver(checkScroll);
    resizeObserver.observe(scrollContainer);
    for (const chip of scrollContainer.children) resizeObserver.observe(chip);
    // uploads need a Gooey session, which this page doesn't have: take the prompt to
    // /new as a draft, to attach the files there before sending
    attachButton.addEventListener("click", () =>
      goToNewPage("draft", textarea.value.trim())
    );
    micButton.addEventListener("click", () => dictation.toggleRecording());
    sendButton.addEventListener("click", submit);
    // the back button can restore this page as it was left, mid-submit
    window.addEventListener("pageshow", (event) => {
      if (!event.persisted) return;
      isSubmitting = false;
      render();
    });

    autoResize(textarea);
    render();

    function submit() {
      const prompt = textarea.value.trim();
      if (!prompt || isSubmitting) return;
      goToNewPage("q", prompt);
    }

    function goToNewPage(param, prompt) {
      dictation?.stopRecording();
      isSubmitting = true;
      error = null;
      render();
      window.location.assign(newPageUrl(param, prompt));
    }

    function setValue(value) {
      textarea.value = value;
      onValueChange();
    }

    function onValueChange() {
      autoResize(textarea);
      render();
    }

    function checkScroll() {
      const { scrollLeft, scrollWidth, clientWidth } = scrollContainer;
      const canScrollLeft = scrollLeft > 1;
      const canScrollRight = scrollLeft + clientWidth < scrollWidth - 1;
      fadeLeft.hidden = !canScrollLeft;
      fadeRight.hidden = !canScrollRight;
      suggestions.classList.toggle(
        "ask-gooey-suggestions--left",
        canScrollLeft
      );
      suggestions.classList.toggle(
        "ask-gooey-suggestions--right",
        canScrollRight
      );
    }

    function render() {
      const canSubmit = textarea.value.trim().length > 0 && !isSubmitting;
      inputBar.classList.toggle("ask-gooey-input-bar--focused", isFocused);
      errorBox.hidden = !error;
      // rewriting an alert's text, even unchanged, can have it read out again
      if (errorBox.textContent !== (error || "")) {
        errorBox.textContent = error || "";
      }
      textarea.disabled = isSubmitting;
      attachButton.disabled = isSubmitting;
      micButton.disabled = isSubmitting || micState === "connecting";
      micButton.className = micButtonClass(micState);
      micButton.setAttribute(
        "aria-label",
        micState === "recording" ? "Stop dictation" : "Dictate with microphone"
      );
      setIcon(micButton, micIconName(micState));
      sendButton.disabled = !canSubmit;
      sendButton.classList.toggle("ask-gooey-send-btn--active", canSubmit);
      setIcon(sendButton, isSubmitting ? "spinner" : "arrowUp");
    }
  }

  // useLiveTranscription's counterpart. The app's dictation needs a signed-in session,
  // so this uses the browser's own speech recognition, where there is one.
  function createDictation({ getValue, setValue, setMicState, setError }) {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) return null;
    let recognition = null;
    let isRecording = false;

    return { toggleRecording, stopRecording };

    function toggleRecording() {
      if (recognition) {
        stopRecording();
        return;
      }
      setMicState("connecting");
      setError(null);
      // seed the transcript with whatever is already typed
      const value = getValue();
      let committedText = value.trim() ? value.replace(/\s+$/, "") + " " : "";
      const current = new SpeechRecognition();
      current.continuous = true;
      current.interimResults = true;
      current.onstart = () => {
        isRecording = true;
        setMicState("recording");
        playCue("start");
      };
      current.onresult = (event) => {
        // a stopped session can still deliver its last words, unless a new one began
        if (recognition && recognition !== current) return;
        let partialText = "";
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i];
          if (!result.isFinal) {
            partialText += result[0].transcript;
            continue;
          }
          const transcript = result[0].transcript.trim();
          if (transcript) committedText += transcript + " ";
        }
        setValue(committedText + partialText);
      };
      current.onerror = (event) => {
        if (event.error === "no-speech" || event.error === "aborted") return;
        if (
          ["not-allowed", "service-not-allowed", "audio-capture"].includes(
            event.error
          )
        ) {
          setError("Could not access the microphone. Try again.");
        } else {
          setError("Transcription failed. Try again.");
        }
      };
      current.onend = () => {
        if (recognition === current) stopRecording();
      };
      recognition = current;
      try {
        current.start();
      } catch (err) {
        console.error(err);
        stopRecording();
        setError("Could not access the microphone. Try again.");
      }
    }

    function stopRecording() {
      setMicState("idle");
      const current = recognition;
      recognition = null;
      if (!current) return;
      current.stop();
      if (!isRecording) return;
      isRecording = false;
      playCue("stop");
    }
  }

  // ?q= sends the prompt, ?draft= only fills it in
  function newPageUrl(param, prompt) {
    if (!prompt) return NEW_PAGE_URL;
    const value = clipToEncodedLength(prompt, MAX_ENCODED_PROMPT_LENGTH);
    return `${NEW_PAGE_URL}?${param}=${encodeURIComponent(value)}`;
  }

  // cuts between code points, so an emoji's surrogate pair is never split
  function clipToEncodedLength(text, maxLength) {
    // a lone surrogate would make encodeURIComponent throw
    text = text.toWellFormed?.() ?? text;
    let length = 0;
    let end = 0;
    for (const char of text) {
      length += encodeURIComponent(char).length;
      if (length > maxLength) break;
      end += char.length;
    }
    return text.slice(0, end);
  }

  function truncateSuggestion(prompt) {
    if (prompt.length <= SUGGESTION_CHARACTER_LIMIT) return prompt;
    return `${prompt.slice(0, SUGGESTION_CHARACTER_LIMIT).trimEnd()}...`;
  }

  function micButtonClass(micState) {
    if (micState === "recording") {
      return "ask-gooey-mic-btn ask-gooey-mic-btn--recording";
    }
    if (micState === "connecting") {
      return "ask-gooey-mic-btn ask-gooey-mic-btn--connecting";
    }
    return "ask-gooey-mic-btn";
  }

  function micIconName(micState) {
    if (micState === "connecting") return "spinner";
    if (micState === "recording") return "microphoneRecording";
    return "microphone";
  }

  // swaps only on change, so a running animation isn't restarted on every keystroke
  function setIcon(button, name) {
    if (button.dataset.icon === name) return;
    button.dataset.icon = name;
    button.innerHTML = icon(name);
  }

  function autoResize(el) {
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }

  // short synthesized earcons so we don't need to ship audio assets:
  // mimics the ios dictation cue - a bright pair of pure tones that rise
  // when listening starts and fall when it stops
  function playCue(kind) {
    try {
      const ctx = new AudioContext();
      // bright, high sine notes ~A5 and ~D6 (a perfect fourth) like ios
      let notes;
      if (kind === "start") {
        notes = [880, 1174.66];
      } else {
        notes = [1174.66, 880];
      }
      const noteDuration = 0.085;
      const gap = 0.06;

      notes.forEach((freq, i) => {
        const startAt = ctx.currentTime + i * gap;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        // pure sine keeps it clean and bell-like, matching ios earcons
        osc.type = "sine";
        osc.frequency.value = freq;
        // very fast attack + short decay for a crisp, tight "ping"
        gain.gain.setValueAtTime(0.0001, startAt);
        gain.gain.exponentialRampToValueAtTime(0.14, startAt + 0.004);
        gain.gain.exponentialRampToValueAtTime(0.0001, startAt + noteDuration);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(startAt);
        osc.stop(startAt + noteDuration);
      });

      const totalMs = ((notes.length - 1) * gap + noteDuration) * 1000;
      setTimeout(() => ctx.close(), totalMs + 100);
    } catch (err) {
      // audio cues are best-effort; never let them break recording
      console.error(err);
    }
  }

  function widgetHtml() {
    return `
<div class="ask-gooey-page">
  <div class="ask-gooey-composer">
    <div role="alert" class="ask-gooey-error" hidden></div>
    <div class="ask-gooey-suggestions">
      <div class="ask-gooey-suggestions-fade ask-gooey-suggestions-fade--left" hidden>
        <button type="button" aria-label="Scroll suggestions left" class="ask-gooey-suggestions-arrow">${icon("chevronLeft")}</button>
      </div>
      <div class="ask-gooey-suggestions-scroll"></div>
      <div class="ask-gooey-suggestions-fade ask-gooey-suggestions-fade--right" hidden>
        <button type="button" aria-label="Scroll suggestions right" class="ask-gooey-suggestions-arrow">${icon("chevronRight")}</button>
      </div>
    </div>
    <div class="ask-gooey-input-bar gooey-orbit-border gooey-orbit-border--strong">
      <div class="ask-gooey-input-bar-inner">
        <textarea rows="1" class="ask-gooey-textarea"></textarea>
        <div class="ask-gooey-toolbar">
          <button type="button" aria-label="Attach files" class="ask-gooey-attach-btn">${icon("plus")}</button>
          <div class="ask-gooey-toolbar-right">
            <button type="button" class="ask-gooey-mic-btn"></button>
            <button type="button" aria-label="Send message" class="ask-gooey-send-btn"></button>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>`;
  }

  function icon(name) {
    const { width, svg, className = "" } = ICONS[name];
    return `<svg class="ask-gooey-icon ${className}" viewBox="0 0 ${width} 512" style="width: ${width / 512}em" aria-hidden="true" focusable="false">${svg}</svg>`;
  }

  // Font faces and registered properties don't work from inside a shadow root, so
  // these go on the page. Inter goes under its own name, leaving any Inter the page
  // loads for itself alone.
  function globalCss() {
    return `
@font-face {
  font-family: "Ask Gooey Inter";
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url(https://fonts.gstatic.com/s/inter/v20/UcC73FwrK3iLTeHuS_nVMrMxCp50SjIa1ZL7W0Q5nw.woff2)
    format("woff2");
  unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA,
    U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193,
    U+2212, U+2215, U+FEFF, U+FFFD;
}

@font-face {
  font-family: "Ask Gooey Inter";
  font-style: normal;
  font-weight: 100 900;
  font-display: swap;
  src: url(https://fonts.gstatic.com/s/inter/v20/UcC73FwrK3iLTeHuS_nVMrMxCp50SjIa25L7W0Q5n-wU.woff2)
    format("woff2");
  unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF,
    U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020,
    U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF;
}

@property --gooey-orbit-angle {
  syntax: "<angle>";
  initial-value: 0deg;
  inherits: false;
}
`;
  }

  // AskGooeyNew.css and gooey-orbit-border.css with the values /new ends up computing,
  // which the app's global css (Bootstrap's reboot, custom.css) bends in places:
  // buttons are reset, fields go to 16px on mobile, and so on. Sizes are px, since rem
  // would follow the host page's root font size. Left out: the heading, the page
  // layout, and anything painted in /new's background colour - the chips fade out
  // through a mask instead, so any background (gradients, patterns) shows through -
  // and the mobile swap that puts the chips above the input, which is for /new's
  // composer pinned to the bottom of the screen.
  function widgetCss() {
    return `
:host {
  all: initial;
  display: block;
}

[hidden] {
  display: none !important;
}

*,
*::before,
*::after {
  box-sizing: border-box;
}

button {
  -webkit-appearance: none;
  appearance: none;
  margin: 0;
  padding: 0;
  border: none;
  border-radius: 0;
  background: none;
  box-shadow: none;
  color: inherit;
  font: inherit;
  text-align: inherit;
  text-transform: none;
  cursor: pointer;
}

button:focus:not(:focus-visible) {
  outline: 0;
}

.ask-gooey-page {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  font-family: "Ask Gooey Inter", Inter, sans-serif;
  font-size: 16px;
  font-weight: 400;
  line-height: 1.5;
  color: #000;
  text-align: start;
  -webkit-text-size-adjust: 100%;
  -webkit-tap-highlight-color: transparent;
}

.ask-gooey-composer {
  max-width: 840px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 28px;
  width: 100%;
}

.ask-gooey-error {
  text-align: center;
  font-size: 14.4px;
  color: #dc3545;
}

/* Input first, chips below (DOM is chips then input). */
.ask-gooey-suggestions {
  order: 2;
  position: relative;
  width: 100%;
}

.ask-gooey-input-bar {
  order: 1;
  width: 100%;
  border-radius: 16px;
  padding: 1px;
  background: linear-gradient(135deg, #5ee6d0 0%, #b7c8fe 50%, #e3e0f9 100%);
  box-shadow: 0 0 6px rgba(94, 230, 208, 0.3);
  transition: box-shadow 0.15s ease;
  display: flex;
  flex-direction: column;
}

.ask-gooey-input-bar--focused {
  box-shadow: 0 0 10px rgba(94, 230, 208, 0.5);
}

.ask-gooey-input-bar-inner {
  position: relative;
  z-index: 1;
  width: 100%;
  background: rgba(255, 255, 255, 0.99);
  border-radius: 15.5px;
  padding: 16px 8px 8px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ask-gooey-input-bar.gooey-orbit-border::before {
  padding: 4px;
}

.ask-gooey-textarea {
  width: 100%;
  min-height: 24px;
  max-height: 240px;
  margin: 0;
  background: transparent;
  border: none;
  border-radius: 6px;
  outline: none;
  color: #4b587a;
  font-size: 14px;
  line-height: 20px;
  resize: none;
  padding: 0;
  font-family: "Ask Gooey Inter", Inter, sans-serif;
  overflow: hidden;
}

.ask-gooey-textarea:not(:placeholder-shown) {
  color: #000;
}

.ask-gooey-textarea:disabled {
  background-color: rgba(0, 0, 0, 0.05);
}

.ask-gooey-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  height: 36px;
}

.ask-gooey-toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ask-gooey-attach-btn,
.ask-gooey-mic-btn,
.ask-gooey-send-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  cursor: pointer;
}

.ask-gooey-attach-btn {
  background: none;
  padding: 5px;
  color: #000;
  width: 24px;
  height: 24px;
  border-radius: 8px;
}

.ask-gooey-attach-btn svg {
  font-size: 14px;
}

.ask-gooey-mic-btn {
  background: none;
  padding: 0;
  color: #0a1021;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  transition: background 0.2s ease, color 0.2s ease;
}

.ask-gooey-mic-btn svg,
.ask-gooey-send-btn svg {
  font-size: 16px;
}

.ask-gooey-mic-btn--recording {
  background: #fdecec;
  color: #dc3545;
}

.ask-gooey-mic-btn--connecting {
  cursor: not-allowed;
  opacity: 0.6;
}

.ask-gooey-send-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: none;
  color: #8994b1;
  cursor: not-allowed;
  transition: background 0.2s ease, color 0.2s ease;
}

.ask-gooey-send-btn--active {
  background: #000;
  color: #fff;
  cursor: pointer;
}

.ask-gooey-suggestions-scroll {
  display: flex;
  gap: 12px;
  width: 100%;
  overflow-x: auto;
  padding-bottom: 4px;
  align-items: center;
  scrollbar-width: none;
  -ms-overflow-style: none;
}

.ask-gooey-suggestions-scroll::-webkit-scrollbar {
  display: none;
}

.ask-gooey-suggestions-scroll > :first-child {
  margin-left: auto;
}

.ask-gooey-suggestions-scroll > :last-child {
  margin-right: auto;
}

.ask-gooey-suggestion-chip {
  background: #fff;
  border: 1px solid #eaeaea;
  border-radius: 16px;
  padding: 6px 12px;
  font-size: 13px;
  color: #000;
  white-space: nowrap;
  cursor: pointer;
  transition: background 0.2s ease;
}

.ask-gooey-suggestion-chip:hover {
  background: #f9f9f9;
}

.ask-gooey-suggestions-fade {
  position: absolute;
  top: 0;
  bottom: 4px;
  width: 80px;
  display: flex;
  align-items: center;
  pointer-events: none;
  z-index: 1;
}

.ask-gooey-suggestions-fade--left {
  left: 0;
  justify-content: flex-start;
}

.ask-gooey-suggestions-fade--right {
  right: 0;
  justify-content: flex-end;
}

/* /new paints these fades in its page colour over the chips; masking the chips out
   instead fades them over the same 80px, into whatever is behind the widget. */
.ask-gooey-suggestions--left .ask-gooey-suggestions-scroll {
  --ask-gooey-fade-left: linear-gradient(to right, transparent 32px, #000 80px);
}

.ask-gooey-suggestions--right .ask-gooey-suggestions-scroll {
  --ask-gooey-fade-right: linear-gradient(to left, transparent 32px, #000 80px);
}

.ask-gooey-suggestions--left .ask-gooey-suggestions-scroll,
.ask-gooey-suggestions--right .ask-gooey-suggestions-scroll {
  -webkit-mask-image: var(--ask-gooey-fade-left, linear-gradient(#000 0 0)),
    var(--ask-gooey-fade-right, linear-gradient(#000 0 0));
  -webkit-mask-composite: source-in;
  mask-image: var(--ask-gooey-fade-left, linear-gradient(#000 0 0)),
    var(--ask-gooey-fade-right, linear-gradient(#000 0 0));
  mask-composite: intersect;
}

.ask-gooey-suggestions-arrow {
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px 4px 8px 16px;
  color: #000;
  pointer-events: auto;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ask-gooey-suggestions-fade--left .ask-gooey-suggestions-arrow {
  padding: 8px 16px 8px 4px;
}

.ask-gooey-suggestions-arrow svg {
  font-size: 14px;
}

.ask-gooey-icon {
  display: inline-block;
  height: 1em;
  overflow: visible;
  fill: currentColor;
}

@media (max-width: 991.98px) {
  .ask-gooey-composer {
    gap: 12px;
  }

  /* Safari on iOS zooms the page into a focused field under 16px (custom.css). */
  .ask-gooey-textarea {
    font-size: 16px;
  }
}

/* gooey-orbit-border.css: a cyan comet that sweeps around the input's border twice,
   then fades out. */
.gooey-orbit-border {
  position: relative;
}

.gooey-orbit-border::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  padding: 1.5px;
  background: conic-gradient(
    from var(--gooey-orbit-angle),
    rgba(3, 218, 197, 0.35) 0deg,
    rgba(3, 218, 197, 0.35) 70deg,
    rgba(3, 218, 197, 0.9) 130deg,
    #a5ffee 160deg,
    rgba(3, 218, 197, 0.9) 190deg,
    rgba(3, 218, 197, 0.35) 250deg,
    rgba(3, 218, 197, 0.35) 360deg
  );
  -webkit-mask:
    linear-gradient(#fff 0 0) content-box,
    linear-gradient(#fff 0 0);
  -webkit-mask-composite: xor;
  mask:
    linear-gradient(#fff 0 0) content-box,
    linear-gradient(#fff 0 0);
  mask-composite: exclude;
  pointer-events: none;
  animation:
    gooey-orbit-spin 2.8s linear 2,
    gooey-orbit-fade 5.6s ease-out forwards;
}

.gooey-orbit-border--strong::before {
  padding: 2.5px;
  background: conic-gradient(
    from var(--gooey-orbit-angle),
    transparent 0deg,
    transparent 105deg,
    rgba(3, 218, 197, 0.55) 135deg,
    #03dac5 150deg,
    #ffffff 160deg,
    #03dac5 170deg,
    rgba(3, 218, 197, 0.55) 185deg,
    transparent 215deg,
    transparent 360deg
  );
  filter:
    drop-shadow(0 0 4px #03dac5)
    drop-shadow(0 0 10px rgba(3, 218, 197, 0.9));
}

@keyframes gooey-orbit-spin {
  to {
    --gooey-orbit-angle: 360deg;
  }
}

@keyframes gooey-orbit-fade {
  0%,
  85% {
    opacity: 1;
  }
  100% {
    opacity: 0;
  }
}

/* Font Awesome's animations, as the kit draws them. */
.fa-spin {
  animation: fa-spin 2s linear infinite;
}

.fa-beat-fade {
  animation: fa-beat-fade 1s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

@keyframes fa-spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

@keyframes fa-beat-fade {
  0%,
  100% {
    opacity: 0.4;
    transform: scale(1);
  }
  50% {
    opacity: 1;
    transform: scale(1.125);
  }
}

@media (prefers-reduced-motion: reduce) {
  .gooey-orbit-border::before {
    animation: none;
  }

  .fa-spin,
  .fa-beat-fade {
    animation-delay: -1ms;
    animation-duration: 1ms;
    animation-iteration-count: 1;
  }
}
`;
  }
})();
