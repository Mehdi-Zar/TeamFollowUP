/**
 * Leave-type label localisation.
 *
 * Leave types are stored as free-text French labels in the DB, so translation
 * happens here on the client rather than via the i18n dictionary. Provides the
 * display string for a leave type (and its optional free-text detail).
 */

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

/**
 * Localised label for a leave type. In English, appends the French original in
 * parentheses ("Paid leave (Congés payés)"); in French (or for unknown/custom
 * labels) returns the raw label unchanged.
 */
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
