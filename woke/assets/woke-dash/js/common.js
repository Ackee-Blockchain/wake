// region resizing
const container = document.querySelector('.container');
const leftDiv = document.querySelector('#myDeclDiv');
const rightDiv = document.querySelector('#myRefDiv');
const resizer = document.querySelector('#resizer');

let isResizing = false;
let lastDownX = 0;

resizer.addEventListener('mousedown', (e) => {
    isResizing = true;
    lastDownX = e.clientX;
});

document.addEventListener('mousemove', (e) => {
    if (!isResizing) return;

    const offset = e.clientX - lastDownX;
    const newLeftWidth = leftDiv.offsetWidth + offset;
    const newRightWidth = rightDiv.offsetWidth - offset;

    leftDiv.style.width = `${newLeftWidth}px`;
    rightDiv.style.width = `${newRightWidth}px`;
    window.myDeclGraph.requestUpdate();
    window.myRefGraph.requestUpdate();

    lastDownX = e.clientX;
});

document.addEventListener('mouseup', () => {
    isResizing = false;
});
// endregion resizing

// region modal
$(document).ready(function() {

    // Add a keyboard shortcut listener
    $(document).keydown(function(e) {
        // Key code for "?" is 191
        if (e.keyCode == 191) {
            // Prevent the default action (e.g., entering "?" into a text field)
            e.preventDefault();

            // Open the modal
            $('.ui.overlay.fullscreen.modal').modal('show');
        }
    });
});
// endregion modal

// region fomantic-ui hover
$('button')
    .popup()
    ;
// endregion fomantic-ui hover

// region utils
const $$ = go.GraphObject.make;

function iterator_to_array(it) {
    ret = []
    while (it.next()) {
        ret.push(it.value)
    }
    return ret
}

// endregion utils
