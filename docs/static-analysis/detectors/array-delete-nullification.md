# Array delete nullification detector

Name: `array-delete-nullification`

Using `delete` on array elements only nullifies the element instead of removing it from the array.
This can lead to confusion if developers expect the array to be shortened.

## Example

```solidity hl_lines="7" linenums="1"
pragma solidity ^0.8.0;

contract Example {
    uint[] public numbers = [1, 2, 3, 4, 5];

    function deleteNumber(uint index) public {
        delete numbers[index]; // (1)!
        // If index was 2, array would be [1, 2, 0, 4, 5]
    }
}
```

1. The `delete` statement sets `numbers[index]` to 0 but does not remove it from the array or reduce the array length.

## False positives

Reports may be intentional when implementing "soft delete" patterns, managing fixed-size arrays, or clearing sensitive data while preserving array structure.

## False negatives

May miss cases where array elements are nullified through direct assignment or complex expressions.

## Best practices

To actually remove an element from an array, use "swap and pop" for unordered arrays:

```solidity
function removeElement(uint index) public {
    myArray[index] = myArray[myArray.length - 1];
    myArray.pop();
}
```

## Parameters

The detector does not accept any additional parameters.
```