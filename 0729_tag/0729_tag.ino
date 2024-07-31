#include "dw3000.h"

#define APP_NAME "0729 TAG"
#define ALL_MSG_COMMON_LEN 10
#define ALL_MSG_SN_IDX 1
#define RNG_DELAY_MS 5000

// connection pins
const uint8_t PIN_RST = 27; // reset pin
const uint8_t PIN_IRQ = 34; // irq pin
const uint8_t PIN_SS = 4;   // spi select pin

/* Default communication configuration. We use default non-STS DW mode. */
static dwt_config_t config = {
    9,                /* Channel number. */
    DWT_PLEN_128,     /* Preamble length. Used in TX only. */
    DWT_PAC8,         /* Preamble acquisition chunk size. Used in RX only. */
    9,                /* TX preamble code. Used in TX only. */
    9,                /* RX preamble code. Used in RX only. */
    1,                /* 0 to use standard 8 symbol SFD, 1 to use non-standard 8 symbol, 2 for non-standard 16 symbol SFD and 3 for 4z 8 symbol SDF type */
    DWT_BR_6M8,       /* Data rate. */
    DWT_PHRMODE_STD,  /* PHY header mode. */
    DWT_PHRRATE_STD,  /* PHY header rate. */
    (129 + 8 - 8),    /* SFD timeout (preamble length + 1 + SFD length - PAC size). Used in RX only. */
    DWT_STS_MODE_OFF, /* STS disabled */
    DWT_STS_LEN_64,   /* STS length see allowed values in Enum dwt_sts_lengths_e */
    DWT_PDOA_M0       /* PDOA mode off */
};

static uint8_t rx_buffer[FRAME_LEN_MAX];
static uint8_t rx_a1_msg[] = {0xC5, 0, 'A', 'N', 'C', 'H', 'O', 'R', 0, 1};
static uint8_t rx_a2_msg[] = {0xC5, 0, 'A', 'N', 'C', 'H', 'O', 'R', 0, 2};
static uint8_t rx_a3_msg[] = {0xC5, 0, 'A', 'N', 'C', 'H', 'O', 'R', 0, 3};
static uint8_t rx_a4_msg[] = {0xC5, 0, 'A', 'N', 'C', 'H', 'O', 'R', 0, 4};

bool anchor1_received = false;
bool anchor2_received = false;
bool anchor3_received = false;
bool anchor4_received = false;

uint32_t status_reg;
uint16_t frame_len;

void setup()
{
  UART_init();
  test_run_info((unsigned char *)APP_NAME);

  /* Configure SPI rate, DW3000 supports up to 38 MHz */
  /* Reset DW IC */
  spiBegin(PIN_IRQ, PIN_RST);
  spiSelect(PIN_SS);

  delay(200); // Time needed for DW3000 to start up (transition from INIT_RC to IDLE_RC, or could wait for SPIRDY event)

  while (!dwt_checkidlerc()) // Need to make sure DW IC is in IDLE_RC before proceeding
  {
    UART_puts("IDLE FAILED\r\n");
    while (1)
      ;
  }

  dwt_softreset();
  delay(200);

  if (dwt_initialise(DWT_DW_INIT) == DWT_ERROR)
  {
    UART_puts("INIT FAILED\r\n");
    while (1)
      ;
  }

  // Enabling LEDs here for debug so that for each TX the D1 LED will flash on DW3000 red eval-shield boards.
  dwt_setleds(DWT_LEDS_ENABLE | DWT_LEDS_INIT_BLINK);

  // Configure DW IC. See NOTE 5 below.
  if (dwt_configure(&config)) // if the dwt_configure returns DWT_ERROR either the PLL or RX calibration has failed the host should reset the device
  {
    UART_puts("CONFIG FAILED\r\n");
    while (1)
      ;
  }
}

void loop()
{
  memset(rx_buffer, 0, sizeof(rx_buffer));

  dwt_rxenable(DWT_START_RX_IMMEDIATE);

  while (!((status_reg = dwt_read32bitreg(SYS_STATUS_ID)) & (SYS_STATUS_RXFCG_BIT_MASK | SYS_STATUS_ALL_RX_ERR)))
  {
  };

  if (status_reg & SYS_STATUS_RXFCG_BIT_MASK)
  {
    frame_len = dwt_read32bitreg(RX_FINFO_ID) & RXFLEN_MASK;
    if (frame_len <= FRAME_LEN_MAX)
    {
      dwt_readrxdata(rx_buffer, frame_len, 0);
      rx_buffer[ALL_MSG_SN_IDX] = 0;

      //Anchor 1
      if(memcmp(rx_buffer, rx_a1_msg, ALL_MSG_COMMON_LEN) == 0 || anchor1_received == false)
      {
        test_run_info((unsigned char *)"This frame is from Anchor1");
        anchor1_received = true;
      }
      //Anchor 2
      else if(memcmp(rx_buffer, rx_a2_msg, ALL_MSG_COMMON_LEN) == 0 || anchor2_received == false)
      {
        test_run_info((unsigned char *)"This frame is from Anchor2");
        anchor2_received = true;
      }
      //Anchor 3
      else if(memcmp(rx_buffer, rx_a3_msg, ALL_MSG_COMMON_LEN) == 0 || anchor3_received == false)
      {
        test_run_info((unsigned char *)"This frame is from Anchor3");
        anchor3_received = true;
      }
      //Anchor 4
      else if(memcmp(rx_buffer, rx_a4_msg, ALL_MSG_COMMON_LEN) == 0 || anchor4_received == false)
      {
        test_run_info((unsigned char *)"This frame is from Anchor4");
        anchor4_received = true;
      }

      if (anchor1_received && anchor2_received && anchor3_received && anchor4_received)
      {
        // Reset flags
        anchor1_received = false;
        anchor2_received = false;
        anchor3_received = false;
        anchor4_received = false;

        // Execute a delay before the next round of reception
        Sleep(RNG_DELAY_MS);
      }

      dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);
    }
  }
  else
  {
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_ERR);
  }
}
