# Given ToA values in the image, we'll convert them to seconds using the conversion factor.

# Define the conversion factor
TIMESTAMP_CONVERSION_FACTOR = 1 / (128 * 499.2 * 10**6)

# ToA values from the image
toa_values = [
    [1927794957827.4485, 1927794957345.9966, 1927794957627.25, 1927794957754.2573],
    [2426958875626.7935, 2426958875060.5654, 2426958875093.4834, 2426958876259.842],
    [8506133054301.805, 8506133053931.661, 8506133053987.307, 8506133055060.712]
]

# Convert ToA values to seconds
toa_seconds = [[value * TIMESTAMP_CONVERSION_FACTOR for value in row] for row in toa_values]
print(toa_seconds)