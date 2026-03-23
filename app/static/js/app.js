const PASSWORD_PATTERN = /^(?=.*[A-Z])(?=.*\d)(?=.*[^A-Za-z0-9]).{8,}$/;

function togglePasswordVisibility(button) {
  const targetId = button.dataset.target;
  const input = document.getElementById(targetId);
  if (!input) {
    return;
  }

  const isPassword = input.type === "password";
  input.type = isPassword ? "text" : "password";
  button.textContent = isPassword ? button.dataset.hideLabel : button.dataset.showLabel;
}

function updatePasswordStatus() {
  const password = document.getElementById("password");
  const confirm = document.getElementById("confirm_password");
  const status = document.getElementById("password-status");
  const button = document.getElementById("create-account-button");

  if (!password || !confirm || !status || !button) {
    return;
  }

  if (!password.value && !confirm.value) {
    status.textContent = "";
    button.disabled = true;
    return;
  }

  const valid = PASSWORD_PATTERN.test(password.value) && password.value === confirm.value;
  status.textContent = valid ? status.dataset.trueLabel : status.dataset.falseLabel;
  status.className = valid ? "field-feedback success" : "field-feedback error";
  button.disabled = !valid;
}

function updateResetPasswordStatus() {
  const password = document.getElementById("new_password");
  const confirm = document.getElementById("confirm_new_password");
  const status = document.getElementById("reset-password-status");
  const button = document.getElementById("reset-password-button");

  if (!password || !confirm || !status || !button) {
    return;
  }

  if (!password.value && !confirm.value) {
    status.textContent = "";
    button.disabled = true;
    return;
  }

  const valid = PASSWORD_PATTERN.test(password.value) && password.value === confirm.value;
  status.textContent = valid ? status.dataset.trueLabel : status.dataset.falseLabel;
  status.className = valid ? "field-feedback success" : "field-feedback error";
  button.disabled = !valid;
}

async function checkUsernameAvailability(input) {
  const feedback = document.getElementById("username-feedback");
  if (!feedback || !input.value.trim()) {
    if (feedback) {
      feedback.textContent = "";
      feedback.className = "field-feedback";
    }
    return;
  }

  const url = new URL(input.dataset.availabilityUrl, window.location.origin);
  url.searchParams.set("username", input.value.trim());
  const response = await fetch(url.toString(), {
    headers: { "X-Requested-With": "fetch" },
  });
  const payload = await response.json();
  feedback.textContent = payload.message;
  feedback.className = payload.available ? "field-feedback success" : "field-feedback error";
}

document.querySelectorAll(".toggle-password").forEach((button) => {
  button.addEventListener("click", () => togglePasswordVisibility(button));
});

const languageSelector = document.querySelector("[data-language-selector='true']");
if (languageSelector && languageSelector.form) {
  languageSelector.addEventListener("change", () => {
    languageSelector.form.submit();
  });
}

["password", "confirm_password"].forEach((fieldId) => {
  const field = document.getElementById(fieldId);
  if (field) {
    field.addEventListener("input", updatePasswordStatus);
  }
});

["new_password", "confirm_new_password"].forEach((fieldId) => {
  const field = document.getElementById(fieldId);
  if (field) {
    field.addEventListener("input", updateResetPasswordStatus);
  }
});

const usernameInput = document.getElementById("username");
if (usernameInput && usernameInput.dataset.availabilityUrl) {
  usernameInput.addEventListener("blur", () => {
    checkUsernameAvailability(usernameInput).catch(() => {
      const feedback = document.getElementById("username-feedback");
      if (feedback) {
        feedback.textContent = "";
      }
    });
  });
}
