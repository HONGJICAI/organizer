<container>
	<slot></slot>
</container>

<style>
	container {
		display: flex;
		justify-content: flex-start;
		align-items: center;
		/* can scroll to right inside this */
		overflow-x: visible;
		overflow-y: hidden;
		/* beauty scroll bar */
		scrollbar-width: thin;
		scrollbar-color: #888 #f1f1f1;
	}
</style>
