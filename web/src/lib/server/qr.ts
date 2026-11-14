/** QR codes as inline SVG, for "Scan with your phone" on the start page and the phone frame. */
import QRCode from 'qrcode';

export function qrSvg(text: string): Promise<string> {
	return QRCode.toString(text, {
		type: 'svg',
		margin: 1,
		errorCorrectionLevel: 'M',
		color: { dark: '#10303f', light: '#ffffff' }
	});
}
