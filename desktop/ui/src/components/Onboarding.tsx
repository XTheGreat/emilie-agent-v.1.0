// First start without an API key: pick a provider, paste the key (like `emilie --setup`, in a window).
import { useStore } from "@/lib/store";
import { EmilieIcon } from "./EmilieIcon";
import { ProviderPanel } from "./SettingsPanels";

export function Onboarding() {
  return (
    <div className="fixed inset-x-0 bottom-0 top-[27px] z-[70] flex justify-center overflow-y-auto bg-bg-100 animate-fade-in">
      <div className="my-auto w-full max-w-[640px] px-8 py-10">
        <div className="mb-6 flex flex-col items-center text-center">
          <EmilieIcon size={96} />
          <h1 className="mt-4 text-[22px] font-semibold text-text-100">Welcome to Emilie</h1>
          <p className="mt-1.5 text-[13px] text-text-400">Choose the AI provider Emilie should use and paste its API key. You can change it later in Settings.</p>
        </div>
        <ProviderPanel compact onDone={() => useStore.getState().refreshState()} />
      </div>
    </div>
  );
}
