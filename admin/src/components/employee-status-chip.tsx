import { Chip } from "@heroui/chip";

import type { EmployeeStatus } from "@/types/employee.types";

const TONE: Record<EmployeeStatus, "default" | "primary" | "success" | "warning" | "danger"> = {
  bench: "default",
  pursuing: "warning",
  placed: "success",
  inactive: "danger",
};

const LABEL: Record<EmployeeStatus, string> = {
  bench: "On bench",
  pursuing: "Pursuing",
  placed: "Placed",
  inactive: "Inactive",
};

export function EmployeeStatusChip({ status }: { status: EmployeeStatus }) {
  return (
    <Chip color={TONE[status]} size="sm" variant="flat">
      {LABEL[status]}
    </Chip>
  );
}
