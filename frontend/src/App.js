import React, { useState, useRef, useEffect } from 'react';
import './App.css';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const EVAL_STATUS_MESSAGES = [
  'Running test queries against the API…',
  'Sending each query to the backend…',
  'Evaluating responses (this may take a minute)…',
  'Checking pass/fail for each test case…',
  'Loading models and building answers…',
  'Almost there…',
];

/** Convert **bold** and *italic* in a string to React nodes */
function formatInlineFormatting(str, keyPrefix = '') {
  if (!str || typeof str !== 'string') return str;
  const result = [];
  const re = /\*\*(.+?)\*\*|\*(.+?)\*/g;
  let lastIndex = 0;
  let match;
  let key = 0;
  while ((match = re.exec(str)) !== null) {
    if (match.index > lastIndex) result.push(str.slice(lastIndex, match.index));
    if (match[1] !== undefined) result.push(<strong key={`${keyPrefix}b-${key++}`}>{match[1]}</strong>);
    else result.push(<em key={`${keyPrefix}i-${key++}`}>{match[2]}</em>);
    lastIndex = re.lastIndex;
  }
  if (lastIndex < str.length) result.push(str.slice(lastIndex));
  return result.length === 1 && typeof result[0] === 'string' ? result[0] : result;
}

/** Format raw assistant text into paragraphs, numbered lists, headings (bold), and source citations */
function formatMessageText(raw) {
  if (!raw || !raw.trim()) return null;
  const blocks = raw.split(/\n\n+/);
  return blocks.map((block, blockIdx) => {
    const trimmed = block.trim();
    if (!trimmed) return null;
    const lines = trimmed.split('\n').filter(Boolean);
    const isNumberedList = lines.length > 0 && lines.every((line) => /^\d+\.\s/.test(line.trim()));
    if (isNumberedList) {
      const items = trimmed.split(/\n(?=\d+\.\s)/).map((item) => {
        const sourceMatch = item.match(/\s*\(?(Source:\s*[^)]+)\)?\.?\s*$/i);
        const citation = sourceMatch ? sourceMatch[0].replace(/^\s*\(?|\)?\.?\s*$/g, '').trim() : null;
        const withoutSource = citation ? item.replace(/\s*\(?(Source:\s*[^)]+)\)?\.?\s*$/i, '').trim() : item;
        const main = withoutSource.replace(/^\d+\.\s*/, '').trim();
        return { main, citation };
      });
      return (
        <ol key={blockIdx} className="message-list">
          {items.map((item, i) => (
            <li key={i} className="message-list-item">
              <span className="message-list-content">{formatInlineFormatting(item.main, `l${i}-`)}</span>
              {item.citation && <span className="message-citation">{item.citation}</span>}
            </li>
          ))}
        </ol>
      );
    }
    const withCitations = trimmed.split(/(\s*\(?Source:\s*[^)]+\)?\.?\s*)/gi).filter(Boolean);
    const parts = withCitations.map((part, i) => {
      if (/^\s*\(?Source:\s*.+\)?\.?\s*$/i.test(part.trim())) {
        return <span key={i} className="message-citation">{part.trim().replace(/^\(|\)\.?\s*$/g, '')}</span>;
      }
      return formatInlineFormatting(part, `p${blockIdx}-${i}-`);
    });
    const isHeading = lines.length === 1 && trimmed.length < 80 && (trimmed.endsWith(':') || /^#+\s/.test(trimmed) || /^Step\s+\d+/i.test(trimmed));
    const className = isHeading ? 'message-paragraph message-heading' : 'message-paragraph';
    return (
      <p key={blockIdx} className={className}>
        {parts.length === 1 ? parts[0] : parts}
      </p>
    );
  }).filter(Boolean);
}

/** Assistant message body with formatted output (no typing animation) */
function FormattedMessageContent({ text = '', streaming, error }) {
  const visible = error ? error : text;
  if (error) {
    return <div className="text message-text-formatted">{visible}</div>;
  }
  const formatted = formatMessageText(visible);
  return (
    <div className="text message-text-formatted">
      {formatted && formatted.length > 0 ? formatted : (visible || '\u00A0')}
      {streaming && <span className="message-cursor" aria-hidden="true">▋</span>}
    </div>
  );
}

function App() {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [errorType, setErrorType] = useState(null); // 'network' | 'other'
  const [messages, setMessages] = useState([]);
  const [lastMeta, setLastMeta] = useState(null);
  const [conversationId, setConversationId] = useState(null);
  const [evalReport, setEvalReport] = useState(null);
  const [evalLoading, setEvalLoading] = useState(false);
  const [evalStatusMessage, setEvalStatusMessage] = useState('');
  const messagesEndRef = useRef(null);
  const messagesContainerRef = useRef(null);
  const inputRef = useRef(null);
  const [backendStatus, setBackendStatus] = useState('checking'); // 'checking' | 'online' | 'offline'

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, loading]);

  const prevLoadingRef = useRef(false);
  useEffect(() => {
    if (prevLoadingRef.current && !loading && inputRef.current) inputRef.current.focus();
    prevLoadingRef.current = loading;
  }, [loading]);

  useEffect(() => {
    const check = async () => {
      try {
        const res = await fetch(`${API_URL}/health`, { method: 'GET' });
        setBackendStatus(res.ok ? 'online' : 'offline');
      } catch {
        setBackendStatus('offline');
      }
    };
    check();
    const interval = setInterval(check, 20000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!evalLoading) {
      setEvalStatusMessage('');
      return;
    }
    setEvalStatusMessage(EVAL_STATUS_MESSAGES[0]);
    let idx = 0;
    const interval = setInterval(() => {
      idx = (idx + 1) % EVAL_STATUS_MESSAGES.length;
      setEvalStatusMessage(EVAL_STATUS_MESSAGES[idx]);
    }, 2800);
    return () => clearInterval(interval);
  }, [evalLoading]);

  const startNewConversation = () => {
    setConversationId(null);
    setMessages([]);
    setLastMeta(null);
    setError(null);
    setErrorType(null);
    setQuestion('');
  };

  const sendQuery = async () => {
    const q = question.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setErrorType(null);
    setMessages((prev) => [...prev, { role: 'user', text: q }]);
    setQuestion('');

    const payload = { question: q };
    if (conversationId) payload.conversation_id = conversationId;

    try {
      const res = await fetch(`${API_URL}/query/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const data = JSON.parse(line);
            if (data.type === 'metadata') {
              setConversationId(data.conversation_id);
              setLastMeta({
                model_used: data.model_used,
                classification: data.classification,
                tokens: {},
                latency_ms: 0,
                chunks_retrieved: data.chunks_retrieved,
                sources: data.sources || [],
                evaluator_flags: [],
              });
              setMessages((prev) => [...prev, { role: 'assistant', text: '', streaming: true }]);
            } else if (data.type === 'token') {
              setMessages((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last?.role === 'assistant') next[next.length - 1] = { ...last, text: last.text + (data.content || '') };
                return next;
              });
            } else if (data.type === 'done') {
              setLastMeta((prev) => ({
                ...prev,
                evaluator_flags: data.evaluator_flags || [],
                tokens: data.tokens || {},
                latency_ms: data.latency_ms ?? prev?.latency_ms,
              }));
              setMessages((prev) => {
                const next = [...prev];
                const last = next[next.length - 1];
                if (last?.role === 'assistant') next[next.length - 1] = { ...last, streaming: false };
                return next;
              });
            }
          } catch (err) {
            // ignore parse errors for incomplete lines
          }
        }
      }
    } catch (e) {
      const message = e.response?.data?.detail || e.message;
      const isNetwork = (e.message === 'Failed to fetch' || e.name === 'TypeError') && !e.response;
      setError(message);
      setErrorType(isNetwork ? 'network' : 'other');
      setMessages((prev) => [...prev, { role: 'assistant', text: null, error: message }]);
    } finally {
      setLoading(false);
    }
  };

  const runEvalHarness = async () => {
    setEvalLoading(true);
    setEvalReport(null);
    try {
      const res = await fetch(`${API_URL}/eval`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      setEvalReport(data);
    } catch (e) {
      setEvalReport({ error: e.message, results: [], total: 0, passed: 0 });
    } finally {
      setEvalLoading(false);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <div className="App-header__title-wrap">
          <span className="App-header__icon" aria-hidden="true">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 8V4H8" />
              <rect x="2" y="10" width="20" height="10" rx="2" />
              <path d="M6 16v-2M10 16v-2M14 16v-2M18 16v-2" />
            </svg>
          </span>
          <h1>Clearpath Support Chat</h1>
        </div>
        <div className="App-header__row">
          <p className="subtitle">Ask a question about Clearpath (project management).</p>
          <div className={`backend-status backend-status--${backendStatus}`} role="status" aria-live="polite">
            <span className="backend-status__dot" aria-hidden="true" />
            <span className="backend-status__text">
              {backendStatus === 'online' && 'Chatbot is online'}
              {backendStatus === 'offline' && 'Backend offline'}
              {backendStatus === 'checking' && 'Checking…'}
            </span>
          </div>
        </div>
      </header>

      <main className="chat-main">
        <div className="messages" ref={messagesContainerRef}>
          {messages.length === 0 && (
            <div className="message assistant message--welcome">
              <span className="role">Clearpath</span>
              <div className="text message-text-formatted">
                <p className="message-paragraph">Hi! I’m the Clearpath support assistant. You can ask me about plans, pricing, the API, workflows, or anything in the docs.</p>
                <p className="message-paragraph">Try: <strong>“What is the Pro plan price?”</strong> or <strong>“How do I create a custom workflow?”</strong></p>
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`message ${m.role}${m.streaming ? ' streaming' : ''}`}>
              <span className="role">{m.role === 'user' ? 'You' : 'Clearpath'}</span>
              {m.role === 'assistant' ? (
                <FormattedMessageContent text={m.text || ''} streaming={m.streaming} error={m.error} />
              ) : (
                <div className="text">{m.text || '…'}</div>
              )}
              {m.role === 'assistant' && m.text && lastMeta && messages[messages.length - 1] === m && (
                <>
                  {lastMeta.evaluator_flags?.length > 0 && (
                    <div className="low-confidence">Low confidence — please verify with support.</div>
                  )}
                  <div className="response-meta">
                    <div className="response-meta__row">
                      <span className="response-meta__item">
                        <span className="response-meta__label">Model</span>
                        <span className="response-meta__value">{lastMeta.model_used}</span>
                      </span>
                      <span className="response-meta__item">
                        <span className="response-meta__label">Tokens</span>
                        <span className="response-meta__value">{lastMeta.tokens?.input ?? '—'}+{lastMeta.tokens?.output ?? '—'}</span>
                      </span>
                      <span className="response-meta__item">
                        <span className="response-meta__label">Chunks</span>
                        <span className="response-meta__value">{lastMeta.chunks_retrieved}</span>
                      </span>
                      <span className="response-meta__item">
                        <span className="response-meta__label">Latency</span>
                        <span className="response-meta__value">{lastMeta.latency_ms}ms</span>
                      </span>
                      {lastMeta.evaluator_flags?.length > 0 && (
                        <span className="response-meta__item response-meta__item--flags">
                          <span className="response-meta__label">Flags</span>
                          <span className="response-meta__value">{lastMeta.evaluator_flags.join(', ')}</span>
                        </span>
                      )}
                    </div>
                    {lastMeta.sources?.length > 0 && (
                      <div className="response-meta__sources">
                        <span className="response-meta__sources-title">Sources</span>
                        <ul className="response-meta__sources-list">
                          {lastMeta.sources.map((src, idx) => (
                            <li key={idx} className="response-meta__source">
                              <span className="response-meta__source-doc" title={src.document}>
                                {(src.document || '').split(/[/\\]/).pop() || src.document || '—'}
                              </span>
                              {src.page != null && <span className="response-meta__source-page">p.{src.page}</span>}
                              {src.relevance_score != null && <span className="response-meta__source-score">{Math.round(src.relevance_score * 100)}%</span>}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          ))}
          {loading && !messages[messages.length - 1]?.streaming && (
            <div className="message assistant message--thinking">
              <span className="role">Clearpath</span>
              <div className="text message-thinking__row">
                <span className="apple-spinner" aria-hidden="true" />
                <span>Thinking…</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} className="messages__end" aria-hidden="true" />
        </div>

        <div className="input-row">
          <button type="button" className="new-chat-btn-inline" onClick={startNewConversation} title="Start a new conversation (clears memory)">
            <span className="new-chat-btn-inline__icon" aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 5v14M5 12h14" />
              </svg>
            </span>
            <span>New chat</span>
          </button>
          <button type="button" className={`eval-btn ${evalLoading ? 'eval-btn--loading' : ''}`} onClick={runEvalHarness} disabled={evalLoading} title="Run test queries and show pass/fail (for demo)">
            <span className="eval-btn__icon" aria-hidden="true">
              {evalLoading ? (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
              )}
            </span>
            <span>{evalLoading ? 'Running eval…' : 'Run eval harness'}</span>
          </button>
          <input
            ref={inputRef}
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && sendQuery()}
            placeholder="Type your question…"
            disabled={loading}
            maxLength={2000}
            aria-label="Ask a question (max 2000 characters)"
          />
          <button onClick={sendQuery} disabled={loading || !question.trim()} className="send-btn" title="Send message">
            <span className="send-btn__icon" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" />
              </svg>
            </span>
            <span className="send-btn__label">Send</span>
          </button>
        </div>

        {error && (
          <div className={`error-box ${errorType === 'network' ? 'error-box--network' : ''}`} role="alert">
            {errorType === 'network' ? (
              <>
                <div className="error-box__icon">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 1l22 22M16.72 11.06A10.94 10.94 0 0119 12.55M5 12.55a10.94 10.94 0 015.17-2.39M10.71 5.05A16 16 0 0122.58 9M1.42 9a15.91 15.91 0 014.7-2.88M8.53 16.11a6 6 0 016.95 0M12 20h.01" />
                  </svg>
                </div>
                <div className="error-box__content">
                  <strong className="error-box__title">Connection problem</strong>
                  <p className="error-box__message">{error}</p>
                  <p className="error-box__hint">Check your network and try again.</p>
                </div>
                <button type="button" className="error-box__dismiss" onClick={() => { setError(null); setErrorType(null); inputRef.current?.focus(); }}>Try again</button>
              </>
            ) : (
              <>
                <div className="error-box__icon error-box__icon--other">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10" /><path d="M12 8v4M12 16h.01" />
                  </svg>
                </div>
                <div className="error-box__content">
                  <strong className="error-box__title">Something went wrong</strong>
                  <p className="error-box__message">{error}</p>
                </div>
                <button type="button" className="error-box__dismiss" onClick={() => { setError(null); setErrorType(null); inputRef.current?.focus(); }}>Try again</button>
              </>
            )}
          </div>
        )}

        {evalLoading && (
          <div className="eval-loading" role="status" aria-live="polite">
            <div className="eval-loading__spinner" aria-hidden="true">
              <span className="apple-spinner apple-spinner--lg" />
            </div>
            <p className="eval-loading__text">Running eval harness…</p>
            <p className="eval-loading__hint">{evalStatusMessage || 'Running test queries against the API…'}</p>
          </div>
        )}

        {evalReport && (
          <details className="eval-panel" open>
            <summary>Eval harness report ({evalReport.error ? 'Error' : `${evalReport.passed}/${evalReport.total} passed`})</summary>
            {evalReport.error ? (
              <p className="eval-error">{evalReport.error}</p>
            ) : (
              <ul className="eval-list">
                {evalReport.results.map((r, i) => (
                  <li key={i} className={r.pass ? 'eval-pass' : 'eval-fail'}>
                    <span className="eval-status">{r.pass ? 'PASS' : 'FAIL'}</span> {r.id}: {r.reason}
                    {r.query && <div className="eval-query">Query: {r.query}</div>}
                    {!r.pass && r.answer_preview && <div className="eval-answer">Answer: {r.answer_preview}</div>}
                    <div className="eval-meta">
                      Model: {r.model_used ?? '—'} · Tokens: {r.tokens_input ?? '—'}+{r.tokens_output ?? '—'} · Chunks: {r.chunks_retrieved ?? '—'} · Latency: {r.latency_ms != null ? `${r.latency_ms}ms` : '—'}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </details>
        )}

        <details className="debug-panel">
          <summary>Debug: last response</summary>
          {lastMeta ? (
            <pre>
              {JSON.stringify(
                {
                  model_used: lastMeta.model_used,
                  classification: lastMeta.classification,
                  tokens: lastMeta.tokens,
                  latency_ms: lastMeta.latency_ms,
                  chunks_retrieved: lastMeta.chunks_retrieved,
                  evaluator_flags: lastMeta.evaluator_flags,
                },
                null,
                2
              )}
            </pre>
          ) : (
            <p>No query sent yet.</p>
          )}
        </details>
      </main>
    </div>
  );
}

export default App;
