/**
 * Phone numbers on the set-up screen: the number the visitor types, as E.164, and the
 * masked form shown everywhere else (`+358 40 *** **12`, CLAUDE.md design rules).
 * Nothing is verified; whoever types the number is treated as its owner (spec §2.1).
 *
 * No imports, so the mock relay can load it straight from Node.
 */

export const COUNTRY_CODES = ['+358', '+46', '+47', '+45', '+372', '+49', '+44', '+1'] as const;

/**
 * Turns what the visitor typed into E.164, or null when it can't be a phone number.
 * A number that starts with `+` or `00` keeps its own country code; otherwise the
 * selected code is used and one leading 0 is dropped ("040 123 4512" → +358401234512).
 */
export function toE164(countryCode: string, typed: string): string | null {
	const raw = typed.trim();
	if (!/^[+\d\s().-]*$/.test(raw)) return null;
	let digits = raw.replace(/[^\d+]/g, '');
	if (digits.indexOf('+') > 0 || (digits.match(/\+/g) ?? []).length > 1) return null;
	let full: string;
	if (digits.startsWith('+')) {
		full = digits;
	} else if (digits.startsWith('00')) {
		full = `+${digits.slice(2)}`;
	} else {
		if (digits.startsWith('0')) digits = digits.slice(1);
		full = `${countryCode}${digits}`;
	}
	return isE164(full) ? full : null;
}

/** `+` and 8 to 15 digits, with a national part of at least 6 digits. */
export function isE164(value: string): boolean {
	if (!/^\+[1-9]\d{7,14}$/.test(value)) return false;
	const code = countryCodeOf(value);
	return value.length - code.length >= 6;
}

/** The country code of an E.164 number: one of ours, or the first 1 to 3 digits. */
export function countryCodeOf(e164: string): string {
	const known = [...COUNTRY_CODES].sort((a, b) => b.length - a.length).find((code) => e164.startsWith(code));
	if (known) return known;
	return e164.slice(0, e164.startsWith('+1') || e164.startsWith('+7') ? 2 : 4);
}

/** `+358 40 *** **12`: the country code, the first two and the last two digits. */
export function maskPhone(e164: string): string {
	const code = countryCodeOf(e164);
	const national = e164.slice(code.length);
	return `${code} ${national.slice(0, 2)} *** **${national.slice(-2)}`;
}
