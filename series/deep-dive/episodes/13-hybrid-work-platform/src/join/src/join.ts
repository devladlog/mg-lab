import { CallClient, Call, CallState as SdkCallState } from "@azure/communication-calling";
import { AzureCommunicationTokenCredential } from "@azure/communication-common";
import { classifyRedeemStatus, describeCallState, parseInvite, redeemMessage, StatusView } from "./state";

interface RedeemResponse {
  token: string;
  userId: string;
  expiresOn: string;
  meetingLink: string;
  displayName: string;
}

const $ = <T extends HTMLElement>(id: string): T => document.getElementById(id) as T;
const statusEl = $<HTMLParagraphElement>("status");
const joinBtn = $<HTMLButtonElement>("join");
const muteBtn = $<HTMLButtonElement>("mute");
const leaveBtn = $<HTMLButtonElement>("leave");
const nameInput = $<HTMLInputElement>("name");

const invite = parseInvite(window.location.hash);
// Take the code out of the address bar and history as soon as we have it.
history.replaceState(null, "", window.location.pathname);

function show(view: StatusView): void {
  statusEl.textContent = view.text;
  statusEl.dataset["tone"] = view.tone;
  muteBtn.disabled = !view.canMute;
  leaveBtn.disabled = !view.canLeave;
}

async function redeem(code: string, displayName: string): Promise<RedeemResponse> {
  let res: Response;
  try {
    res = await fetch("/api/token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, displayName }),
    });
  } catch {
    throw new Error(redeemMessage("network"));
  }
  if (!res.ok) throw new Error(redeemMessage(classifyRedeemStatus(res.status)));
  return (await res.json()) as RedeemResponse;
}

async function joinMeeting(code: string): Promise<void> {
  joinBtn.disabled = true;
  nameInput.disabled = true;
  show({ text: "Checking your invitation...", tone: "info", canMute: false, canLeave: false });
  try {
    const grant = await redeem(code, nameInput.value);

    const callClient = new CallClient();
    const credential = new AzureCommunicationTokenCredential(grant.token);
    const callAgent = await callClient.createCallAgent(credential, { displayName: grant.displayName });

    // Audio only: ask for the microphone, not the camera.
    const deviceManager = await callClient.getDeviceManager();
    const access = await deviceManager.askDevicePermission({ audio: true, video: false });
    if (!access.audio) throw new Error("The microphone is blocked. Allow it in the browser and reload the page.");

    // The meeting link comes from the broker, never from the page URL.
    const call: Call = callAgent.join({ meetingLink: grant.meetingLink }, { audioOptions: { muted: false } });

    const refresh = (): void => {
      const state = call.state as SdkCallState;
      show(describeCallState(state, call.callEndReason?.code, call.callEndReason?.subCode));
      muteBtn.textContent = call.isMuted ? "Unmute" : "Mute";
    };
    call.on("stateChanged", refresh);
    call.on("isMutedChanged", refresh);
    muteBtn.onclick = () => void (call.isMuted ? call.unmute() : call.mute());
    leaveBtn.onclick = () => void call.hangUp();
    refresh();
  } catch (e) {
    joinBtn.disabled = false;
    nameInput.disabled = false;
    show({ text: e instanceof Error ? e.message : "Could not join.", tone: "error", canMute: false, canLeave: false });
  }
}

if (!invite) {
  joinBtn.disabled = true;
  show({ text: "This page needs an invitation link from your host.", tone: "error", canMute: false, canLeave: false });
} else {
  joinBtn.onclick = () => void joinMeeting(invite);
  show({ text: "Enter your name and join.", tone: "info", canMute: false, canLeave: false });
}
