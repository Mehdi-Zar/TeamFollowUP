// Leave types are stored as free-text French labels in the DB. In the English UI
// we show the English translation with the French original in parentheses, e.g.
// "Paid leave (Congés payés)". Custom/unknown labels fall back to the raw label.
const EN_LEAVE_TYPES: Record<string, string> = {
  "Congés payés": "Paid leave",
  "RTT": "RTT",
  "Maladie": "Sick leave",
  "Formation": "Training",
  "Autre": "Other",
};

export function leaveTypeLabel(label: string, lang: string): string {
  if (lang !== "en") return label;
  const en = EN_LEAVE_TYPES[label];
  return en && en !== label ? `${en} (${label})` : label;
}

/** Type label plus its optional free-text detail, e.g. "Autre - Déménagement". */
export function leaveLabel(leave: { type_label: string; detail?: string | null }, lang: string): string {
  const base = leaveTypeLabel(leave.type_label, lang);
  return leave.detail ? `${base} - ${leave.detail}` : base;
}
