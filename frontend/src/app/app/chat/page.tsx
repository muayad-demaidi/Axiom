import { ChatPanel } from "@/components/product/ChatPanel";

export default function ChatPage() {
  return (
    <div className="max-w-3xl">
      <span className="eyebrow">Insight · AI Chat</span>
      <h1 className="text-2xl font-bold mt-2">Ask AXIOM</h1>
      <p className="text-[var(--text-muted)] mt-2">
        Chat with the AI assistant. It detects the language of each message and replies in the same language.
        Streaming via <code>/api/chat/stream</code>.
      </p>
      <div className="mt-6">
        <ChatPanel />
      </div>
    </div>
  );
}
