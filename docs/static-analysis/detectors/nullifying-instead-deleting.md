# Nullifying Instead of Deleting Array Elements

## The addressed problem
Detects when developers use the `delete` operator on array elements, which only nullifies the element instead of removing it from the array.

## The goal of detection
The detector looks for instances where the `delete` operator is used on array elements. While this operation sets the element to its default value (nullifies it), it does not reduce the array length or remove the element from the array. This can lead to confusion and potential bugs if developers expect the array to be shortened.

## Example

```solidity
contract Example {
    uint[] public numbers = [1, 2, 3, 4, 5];

    function deleteNumber(uint index) public {
        delete numbers[index]; // Will set numbers[index] to 0 but won't remove it
        // numbers array will still have the same length
        // If index was 2, array would be [1, 2, 0, 4, 5]
    }
}
```

## Limitations of the detector
The detector only identifies direct usage of the `delete` operator on array elements. It can detect this pattern when used with any type of array (fixed or dynamic size) and any element type.

## False Positives
The detection will be reported even when the nullification is intentional. There are valid use cases where a developer might want to reset an array element to its default value without removing it from the array, such as:
- Implementing a "soft delete" pattern where nullified elements can be reused later
- Managing fixed-size arrays where maintaining the array length is required
- Clearing sensitive data while preserving array structure
- Implementing specific business logic that requires keeping array indices stable

## False Negatives
The detector might miss cases where:
- Array elements are nullified through other means (e.g., direct assignment of default values)
- Complex expressions or function calls are used to achieve the same effect

## Exploitability
This is an informational detection that helps developers write more maintainable and less error-prone code. While not directly exploitable, misunderstanding the behavior of `delete` on array elements can lead to logical errors in contract functionality.

## Best Practices
To actually remove an element from an array:
1. For unordered arrays, use the "swap and pop" pattern:
```solidity
function removeElement(uint index) public {
    require(index < myArray.length);
    myArray[index] = myArray[myArray.length - 1];
    myArray.pop();
}
```

2. For ordered arrays where order matters, shift elements:
```solidity
function removeElement(uint index) public {
    require(index < myArray.length);
    for (uint i = index; i < myArray.length - 1; i++) {
        myArray[i] = myArray[i + 1];
    }
    myArray.pop();
}
```