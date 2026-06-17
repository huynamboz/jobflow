import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation("llm");
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
      setError(err instanceof Error ? err.message : t("providers.errors.save"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onOpenChange={(open) => !open && onClose()} size="md" placement="center">
      <ModalContent>
        <form onSubmit={handleSubmit}>
          <ModalHeader>{provider ? t("providers.modal.editTitle") : t("providers.modal.addTitle")}</ModalHeader>

          <ModalBody className="gap-4">
            {error && (
              <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">{error}</p>
            )}

            <Select
              label={t("providers.modal.clientType")}
              size="sm"
              selectedKeys={[form.client_type]}
              onSelectionChange={(keys) => set("client_type", Array.from(keys)[0] as LLMClientType)}
            >
              <SelectItem key="openai">{t("providers.modal.clientOpenai")}</SelectItem>
              <SelectItem key="messages">{t("providers.modal.clientMessages")}</SelectItem>
            </Select>

            <Input label={t("providers.modal.name")} size="sm" isRequired value={form.name}
              onValueChange={(v) => set("name", v)} placeholder="OpenAI" />

            <Input label={t("providers.modal.model")} size="sm" isRequired value={form.model}
              onValueChange={(v) => set("model", v)} placeholder="gpt-4o-mini" />

            <Input label={t("providers.modal.baseUrl")} size="sm" value={form.base_url}
              onValueChange={(v) => set("base_url", v)} placeholder="https://api.openai.com/v1" />

            <Input
              label={t("providers.modal.apiKey")}
              size="sm"
              type="password"
              isRequired={!provider}
              value={form.api_key}
              onValueChange={(v) => set("api_key", v)}
              placeholder={provider ? t("providers.modal.apiKeyPlaceholderKeep") : t("providers.modal.apiKeyPlaceholderNew")}
              description={provider ? t("providers.modal.apiKeyDescription") : undefined}
            />
          </ModalBody>

          <ModalFooter>
            <Button variant="flat" onPress={onClose}>{t("common:actions.cancel")}</Button>
            <Button type="submit" color="primary" isLoading={saving}>{t("common:actions.save")}</Button>
          </ModalFooter>
        </form>
      </ModalContent>
    </Modal>
  );
}

export default function LLMProvidersPage() {
  const { t } = useTranslation("llm");
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
      setError(err instanceof Error ? err.message : t("providers.errors.activate"));
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
      setTestResults((prev) => ({ ...prev, [id]: { ok: false, message: err instanceof Error ? err.message : t("providers.errors.test") } }));
    } finally {
      setTestingId(null);
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm(t("providers.confirm.delete"))) return;
    setDeletingId(id);
    setError("");
    try {
      await llmService.delete(id);
      setProviders((prev) => prev.filter((p) => p.id !== id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : t("providers.errors.delete"));
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-default-900">{t("providers.title")}</h1>
          <p className="text-default-500">{t("providers.count", { count: providers.length })}</p>
        </div>
        <button
          onClick={() => setModalProvider("new")}
          className="flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          <Plus className="size-4" /> {t("providers.add")}
        </button>
      </div>

      {error && (
        <div className="rounded-lg bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
      )}

      <Card className="shadow-sm">
        <CardBody className="p-0">
          {loading ? (
            <div className="flex items-center justify-center py-16 text-default-400">{t("providers.loading")}</div>
          ) : providers.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-2 py-16 text-default-400">
              <Bot className="size-8" />
              <p>{t("providers.empty")}</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-default-100 bg-default-50 text-xs font-semibold uppercase tracking-wide text-default-500">
                  <tr>
                    <th className="px-4 py-3 text-left">{t("providers.table.name")}</th>
                    <th className="px-4 py-3 text-left">{t("providers.table.model")}</th>
                    <th className="px-4 py-3 text-left">{t("providers.table.baseUrl")}</th>
                    <th className="px-4 py-3 text-left">{t("providers.table.apiKey")}</th>
                    <th className="px-4 py-3 text-left">{t("providers.table.status")}</th>
                    <th className="px-4 py-3 text-left">{t("providers.table.test")}</th>
                    <th className="px-4 py-3 text-left">{t("providers.table.updated")}</th>
                    <th className="px-4 py-3 text-right">{t("providers.table.actions")}</th>
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
                          <span className="rounded-full bg-green-100 px-2.5 py-1 text-xs font-semibold text-green-700">{t("providers.status.active")}</span>
                        ) : (
                          <span className="rounded-full bg-default-100 px-2.5 py-1 text-xs text-default-500">{t("providers.status.inactive")}</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {testResults[p.id] ? (
                          <span className={`flex items-center gap-1 text-xs ${testResults[p.id].ok ? "text-green-600" : "text-red-500"}`}>
                            {testResults[p.id].ok ? <CheckCircle className="size-3.5" /> : <XCircle className="size-3.5" />}
                            {testResults[p.id].ok ? t("providers.test.ok") : t("providers.test.fail")}
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
                            title={t("providers.tooltip.edit")}
                            className="rounded-lg p-1.5 text-default-400 hover:bg-default-100 hover:text-default-700"
                          >
                            <Pencil className="size-4" />
                          </button>
                          <button
                            onClick={() => handleTest(p.id)}
                            disabled={testingId === p.id}
                            title={t("providers.tooltip.test")}
                            className="rounded-lg p-1.5 text-default-400 hover:bg-default-100 hover:text-blue-600 disabled:opacity-40"
                          >
                            {testingId === p.id ? <Loader className="size-4 animate-spin" /> : <Zap className="size-4" />}
                          </button>
                          {!p.is_active && (
                            <button
                              onClick={() => handleActivate(p.id)}
                              disabled={activatingId === p.id}
                              title={t("providers.tooltip.activate")}
                              className="rounded-lg p-1.5 text-default-400 hover:bg-green-50 hover:text-green-600 disabled:opacity-40"
                            >
                              {activatingId === p.id ? <Loader className="size-4 animate-spin" /> : <CheckCircle className="size-4" />}
                            </button>
                          )}
                          <button
                            onClick={() => handleDelete(p.id)}
                            disabled={p.is_active || deletingId === p.id}
                            title={p.is_active ? t("providers.tooltip.cannotDeleteActive") : t("providers.tooltip.delete")}
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
