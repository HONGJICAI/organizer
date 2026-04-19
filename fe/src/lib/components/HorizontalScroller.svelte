<div class="scroller">
	<slot></slot>
</div>

<style>
	.scroller {
		display: flex;
		justify-content: flex-start;
		align-items: center;
		overflow-x: auto;
		overflow-y: hidden;
		scrollbar-width: thin;
		scrollbar-color: #555 #2a2a2a;
		padding-bottom: 0.5rem;
		gap: 0.5rem;
	}
</style>
