import { useEffect, useState } from "react";
import { Card, CardBody } from "@heroui/card";
import { Modal, ModalContent, ModalHeader, ModalBody, ModalFooter } from "@heroui/modal";
import { Input } from "@heroui/input";
import { Button } from "@heroui/button";
import { Select, SelectItem } from "@heroui/select";
import { Bot, CheckCircle, Loader, Pencil, Plus, Trash2, XCircle, Zap } from "lucide-react";

import { llmService } from "@/services/llm.service";
import type { LLMClientType, LLMProvider, LLMProviderWrite } from "@/types/llm.types";

const EMPTY_FORM: LLMProviderWrite = { name: "", api_key: "", model: "", base_url: "", client_type: "openai" };

function ProviderModal({
  isOpen,
  provider,
  onClose,
  onSaved,
}: {
  isOpen: boolean;
  provider: LLMProvider | null;
  onClose: () => void;
  onSaved: (p: LLMProvider) => void;
}) {
  const [form, setForm] = useState<LLMProviderWrite>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setForm(
      provider
        ? { name: provider.name, api_key: "", model: provider.model, base_url: provider.base_url, client_type: provider.client_type }
        : EMPTY_FORM,
    );
    setError("");
  }, [provider, isOpen]);

  const set = (k: keyof LLMProviderWrite, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      const payload = { ...form };
      if (provider && !payload.api_key.trim()) {
        delete (payload as Partial<LLMProviderWrite>).api_key;
      }
      const saved = provider
        ? await llmService.update(provider.id, payload)
        : await llmService.create(payload);
      onSaved(saved);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onOpenChange={(open) => !open && onClose()} size="md" placement="center">
      <ModalContent>
        <form onSubmit={handleSubmit}>
          <ModalHeader>{provider ? "Edit Provider" : "Add Provider"}</ModalHeader>

          <ModalBody className="gap-4">
            {error && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
            )}

            <Select
              label="Client Type"
              size="sm"
              selectedKeys={[form.client_type]}
              onSelectionChange={(keys) => set("client_type", Array.from(keys)[0] as LLMClientType)}
            >
              <SelectItem key="openai">OpenAI Compatible (/chat/completions)</SelectItem>
              <SelectItem key="messages">Messages API (/messages)</SelectItem>
            </Select>

            <Input label="Name" size="sm" isRequired value={form.name}
              onValueChange={(v) => set("name", v)} placeholder="OpenAI" />

            <Input label="Model" size="sm" isRequired value={form.model}
              onValueChange={(v) => set("model", v)} placeholder="gpt-4o-mini" />

            <Input label="Base URL" size="sm" value={form.base_url}
              onValueChange={(v) => set("base_url", v)} placeholder="https://api.openai.com/v1" />

            <Input
              label="API Key"
              size="sm"
              type="password"
              isRequired={!provider}
              value={form.api_key}
              onValueChange={(v) => set("api_key", v)}
              placeholder={provider ? "Leave blank to keep current" : "sk-..."}
              description={provider ? "Leave blank to keep current key" : undefined}
            />
          </ModalBody>

          <ModalFooter>
            <Button variant="flat" onPress={onClose}>Cancel</Button>
            <Button type="submit" color="primary" isLoading={saving}>Save</Button>
          </ModalFooter>
        </form>
      </ModalContent>
    </Modal>
  );
}

export default function LLMProvidersPage() {
  const [providers, setProviders] = useState<LLMProvider[]>([]);
  const [loading, setLoading] = useState(true);
  const [modalProvider, setModalProvider] = useState<LLMProvider | "new" | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testResults, setTestResults] = useState<Record<number, { ok: boolean; message: string }>>({});
  const [activatingId, setActivatingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState("");

  const load = () => {
    setLoading(true);
    llmService.list()
      .then(setProviders)
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleSaved = (saved: LLMProvider) => {
    setProviders((prev) => {
      const idx = prev.findIndex((p) => p.id === saved.id);
      if (idx >= 0) {
        const next = [...prev];
        next[idx] = saved;
        return next;
      }
      return [...prev, saved];
    });
    setModalProvider(null);
  };

  const handleActivate = async (id: number) => {
    setActivatingId(id);
    setError("");
    try {
      const updated = await llmService.activate(id);
      setProviders((prev) => prev.map((p) => ({ ...p, is_active: p.id === updated.id })));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Activate failed.");
    } finally {
      setActivatingId(null);
    }
  };

  const handleTest = async (id: number) => {
    setTestingId(id);
    try {
      const result = await llmService.test(id);
      setTestResults((prev) => ({ ...prev, [id]: result }));
    } catch (err: unknown) {
      setTestResults((prev) => ({ ...prev, [id]: { ok: false, message: err instanceof Error ? err.message : "Test failed." } }));
    } finally {
      setTestingId(null);
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm("Delete this provider?")) return;
    setDeletingId(id);
    setError("");
    try {
      await llmService.delete(id);
      setProviders((prev) => prev.filter((p) => p.id !== id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Delete failed.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-default-900">LLM Providers</h1>
          <p className="text-default-500">{providers.length} provider{providers.length !== 1 ? "s" : ""} configured</p>
        </div>
        <button
          onClick={() => setModalProvider("new")}
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          <Plus className="size-4" /> Add Provider
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
      )}

      <Card className="shadow-sm">
        <CardBody className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-16 text-default-400">Loading…</div>
          ) : providers.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-16 text-default-400">
              <Bot className="size-8" />
              <p>No LLM providers yet.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-default-100 bg-default-50 text-xs font-semibold uppercase tracking-wide text-default-500">
                  <tr>
                    <th className="px-4 py-3 text-left">Name</th>
                    <th className="px-4 py-3 text-left">Model</th>
                    <th className="px-4 py-3 text-left">Base URL</th>
                    <th className="px-4 py-3 text-left">API Key</th>
                    <th className="px-4 py-3 text-left">Status</th>
                    <th className="px-4 py-3 text-left">Test</th>
                    <th className="px-4 py-3 text-left">Updated</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-default-100">
                  {providers.map((p) => (
                    <tr key={p.id} className="transition-colors hover:bg-default-50">
                      <td className="px-4 py-3 font-medium text-default-800">{p.name}</td>
                      <td className="px-4 py-3 font-mono text-xs text-default-600">{p.model}</td>
                      <td className="max-w-[200px] px-4 py-3">
                        <span className="block truncate text-xs text-default-500">{p.base_url}</span>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-default-400">{p.api_key}</td>
                      <td className="px-4 py-3">
                        {p.is_active ? (
                          <span className="rounded-full bg-green-100 px-2.5 py-1 text-xs font-semibold text-green-700">Active</span>
                        ) : (
                          <span className="rounded-full bg-default-100 px-2.5 py-1 text-xs text-default-500">Inactive</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {testResults[p.id] ? (
                          <span className={`flex items-center gap-1 text-xs ${testResults[p.id].ok ? "text-green-600" : "text-red-500"}`}>
                            {testResults[p.id].ok ? <CheckCircle className="size-3.5" /> : <XCircle className="size-3.5" />}
                            {testResults[p.id].ok ? "OK" : "Fail"}
                          </span>
                        ) : (
                          <span className="text-xs text-default-300">—</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-xs text-default-400">
                        {new Date(p.updated_at).toLocaleDateString("vi-VN")}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1">
                          <button
                            onClick={() => setModalProvider(p)}
                            title="Edit"
                            className="rounded-lg p-1.5 text-default-400 hover:bg-default-100 hover:text-default-700"
                          >
                            <Pencil className="size-4" />
                          </button>
                          <button
                            onClick={() => handleTest(p.id)}
                            disabled={testingId === p.id}
                            title="Test connection"
                            className="rounded-lg p-1.5 text-default-400 hover:bg-default-100 hover:text-blue-600 disabled:opacity-40"
                          >
                            {testingId === p.id ? <Loader className="size-4 animate-spin" /> : <Zap className="size-4" />}
                          </button>
                          {!p.is_active && (
                            <button
                              onClick={() => handleActivate(p.id)}
                              disabled={activatingId === p.id}
                              title="Set as active"
                              className="rounded-lg p-1.5 text-default-400 hover:bg-green-50 hover:text-green-600 disabled:opacity-40"
                            >
                              {activatingId === p.id ? <Loader className="size-4 animate-spin" /> : <CheckCircle className="size-4" />}
                            </button>
                          )}
                          <button
                            onClick={() => handleDelete(p.id)}
                            disabled={p.is_active || deletingId === p.id}
                            title={p.is_active ? "Cannot delete active provider" : "Delete"}
                            className="rounded-lg p-1.5 text-default-400 hover:bg-red-50 hover:text-red-500 disabled:cursor-not-allowed disabled:opacity-30"
                          >
                            {deletingId === p.id ? <Loader className="size-4 animate-spin" /> : <Trash2 className="size-4" />}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardBody>
      </Card>

      <ProviderModal
        isOpen={modalProvider !== null}
        provider={modalProvider === "new" ? null : (modalProvider as LLMProvider | null)}
        onClose={() => setModalProvider(null)}
        onSaved={handleSaved}
      />
    </div>
  );
}
