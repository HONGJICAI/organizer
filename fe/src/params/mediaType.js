export function match(value) {
	const supportedMediaTypes = ['comic', 'video', 'image' ];
	return supportedMediaTypes.includes(value);
}
