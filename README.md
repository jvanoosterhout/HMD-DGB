# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/jvanoosterhout/HMD-DGB/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                           |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| DGB/Binder.py                  |      185 |       39 |       66 |        1 |     77% |252-253, 332-338, 376-381, 386-412, 426-446 |
| DGB/ConfigSchema.py            |       92 |        7 |       64 |        7 |     91% |56, 71, 106, 121, 130, 143, 146 |
| DGB/DGBContext.py              |      146 |        1 |       18 |        2 |     98% |173-\>176, 429 |
| DGB/DGBservice.py              |      323 |      112 |       74 |       16 |     62% |140, 145, 170, 178-189, 195-216, 220-225, 269-274, 294, 298, 303, 323, 329-330, 334-337, 344-345, 347-\>exit, 362-365, 371, 374-378, 403-404, 427-431, 439-447, 462-465, 477-480, 487-488, 491-496, 499-501, 512-529, 545-571, 575 |
| DGB/DeviceKeeper.py            |      269 |      143 |      100 |       14 |     42% |38-101, 115-134, 140, 147-\>161, 149-159, 174, 178-\>202, 181-182, 184-185, 189-193, 198-201, 214-221, 231-\>234, 244-248, 249-\>252, 260-\>263, 290-296, 303-328, 331-355, 358-367, 370-385, 388, 391, 394-408, 411-425, 428-442, 445-459, 478-479, 488-493, 523-\>exit |
| DGB/Pin.py                     |       25 |        3 |        0 |        0 |     88% |56, 59, 67 |
| DGB/PinCount.py                |       45 |        5 |        6 |        3 |     84% |81-\>exit, 100-103, 107-114, 116-\>119 |
| DGB/PinIn.py                   |       17 |        9 |        0 |        0 |     47% |27, 34-41, 51-65 |
| DGB/PinKeeper.py               |       74 |        9 |       34 |        5 |     87% |88-89, 112-115, 161-162, 164-165, 189 |
| DGB/PinModels.py               |      109 |       16 |       52 |       17 |     80% |43, 76, 104, 108, 112, 143, 144-\>147, 154-\>156, 160, 164, 168, 174, 178, 184, 188, 193, 232, 279 |
| DGB/PinNWayOut.py              |       61 |       13 |       22 |        6 |     75% |76-77, 81, 83-87, 91-\>90, 94, 127, 133-139, 143 |
| DGB/PinOut.py                  |       63 |       26 |       22 |        5 |     52% |58, 67, 81, 95, 98, 104-131, 135 |
| DGB/SetStateResolver.py        |      165 |       13 |       90 |       11 |     90% |74, 138-139, 141, 157, 161, 197, 215, 221-222, 245, 248-\>254, 318-322 |
| DGB/StartupPolicy.py           |       96 |        0 |        2 |        0 |    100% |           |
| DGB/StartupStateCoordinator.py |      142 |        3 |       66 |        4 |     97% |75, 314-\>320, 327-\>307, 345-349 |
| DGB/SystemDevices.py           |      180 |       39 |       18 |        2 |     78% |229-231, 269-273, 296-300, 354-374, 439-441, 465-466, 474-476 |
| DGB/\_\_init\_\_.py            |        5 |        2 |        0 |        0 |     60% |     20-21 |
| **TOTAL**                      | **1997** |  **440** |  **634** |   **93** | **75%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/jvanoosterhout/HMD-DGB/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/jvanoosterhout/HMD-DGB/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/jvanoosterhout/HMD-DGB/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/jvanoosterhout/HMD-DGB/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fjvanoosterhout%2FHMD-DGB%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/jvanoosterhout/HMD-DGB/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.