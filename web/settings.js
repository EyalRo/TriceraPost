function qs(id) {
  return document.getElementById(id);
}

async function fetchJson(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `Request failed: ${res.status}`);
  }
  return res.json();
}

function setStatus(message, isError = false) {
  const status = qs("save-status");
  if (!status) return;
  status.textContent = message;
  status.style.color = isError ? "#8e2c0a" : "";
}

async function loadSettings() {
  try {
    const settings = await fetchJson("/api/settings");
    qs("nntp-host").value = settings.NNTP_HOST || "";
    qs("nntp-port").value = settings.NNTP_PORT || "";
    qs("nntp-ssl").checked = Boolean(settings.NNTP_SSL);
    qs("nntp-user").value = settings.NNTP_USER || "";
    qs("nntp-lookback").value = settings.NNTP_LOOKBACK || "";
    qs("nntp-groups").value = settings.NNTP_GROUPS || "";

    const passStatus = qs("nntp-pass-status");
    if (passStatus) {
      passStatus.textContent = settings.NNTP_PASS_SET ? "Password stored" : "No password stored";
    }
  } catch (err) {
    setStatus(`Failed to load settings: ${err.message}`, true);
  }
}

function bindForm() {
  const form = qs("settings-form");
  if (!form) return;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    setStatus("Saving...");

    const payload = {
      NNTP_HOST: qs("nntp-host").value.trim(),
      NNTP_PORT: qs("nntp-port").value,
      NNTP_SSL: qs("nntp-ssl").checked,
      NNTP_USER: qs("nntp-user").value.trim(),
      NNTP_LOOKBACK: qs("nntp-lookback").value,
      NNTP_GROUPS: qs("nntp-groups").value.trim(),
      clear_password: qs("nntp-pass-clear").checked,
    };

    const passValue = qs("nntp-pass").value;
    if (passValue) {
      payload.NNTP_PASS = passValue;
    }

    try {
      await fetchJson("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      qs("nntp-pass").value = "";
      qs("nntp-pass-clear").checked = false;
      setStatus("Settings saved.");
      await loadSettings();
    } catch (err) {
      setStatus(`Save failed: ${err.message}`, true);
    }
  });
}

loadSettings();
bindForm();
