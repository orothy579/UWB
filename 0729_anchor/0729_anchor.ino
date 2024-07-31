#include "dw3000.h"
#include <WiFi.h>
#include <HTTPClient.h>

#define APP_NAME "SIMPLE RX v1.1"
#define FRAME_LENGTH (sizeof(tx_msg) + FCS_LEN)  // The real length that is going to be transmitted
#define TX_DELAY_MS 500
#define ALL_MSG_COMMON_LEN 10
#define ALL_MSG_SN_IDX 1

// connection pins
const uint8_t PIN_RST = 27;  // reset pin
const uint8_t PIN_IRQ = 34;  // irq pin
const uint8_t PIN_SS = 4;    // spi select pin
static uint8_t rx_msg[] = { 0xC5, 0, 'S', 'Y', 'N', 'C', 0, 0, 0, 0 };
static uint8_t tx_msg[] = { 0xC5, 0, 'A', 'N', 'C', 'H', 'O', 'R', 0, 1 };


// WiFi credentials
const char* ssid = "AIoT_2F";
const char* password = "monetghgh";

// Server endpoint
const char* serverName = "http://yourserver.com/api/timestamps";

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
uint32_t status_reg;
uint16_t frame_len;

void setup() {
  UART_init();
  test_run_info((unsigned char*)APP_NAME);

  /* Configure SPI rate, DW3000 supports up to 38 MHz */
  /* Reset DW IC */
  spiBegin(PIN_IRQ, PIN_RST);
  spiSelect(PIN_SS);

  delay(200);  // Time needed for DW3000 to start up (transition from INIT_RC to IDLE_RC, or could wait for SPIRDY event)

  while (!dwt_checkidlerc())  // Need to make sure DW IC is in IDLE_RC before proceeding
  {
    UART_puts("IDLE FAILED\r\n");
    while (1)
      ;
  }

  dwt_softreset();
  delay(200);

  if (dwt_initialise(DWT_DW_INIT) == DWT_ERROR) {
    UART_puts("INIT FAILED\r\n");
    while (1)
      ;
  }

  // Enabling LEDs here for debug so that for each TX the D1 LED will flash on DW3000 red eval-shield boards.
  dwt_setleds(DWT_LEDS_ENABLE | DWT_LEDS_INIT_BLINK);

  // Configure DW IC. See NOTE 5 below.
  if (dwt_configure(&config))  // if the dwt_configure returns DWT_ERROR either the PLL or RX calibration has failed the host should reset the device
  {
    UART_puts("CONFIG FAILED\r\n");
    while (1)
      ;
  }

  // Connect to Wi-Fi
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("WiFi connected");
}

void loop() {
  memset(rx_buffer, 0, sizeof(rx_buffer));
  dwt_rxenable(DWT_START_RX_IMMEDIATE);

  while (!((status_reg = dwt_read32bitreg(SYS_STATUS_ID)) & (SYS_STATUS_RXFCG_BIT_MASK | SYS_STATUS_ALL_RX_ERR))) {
  };

  if (status_reg & SYS_STATUS_RXFCG_BIT_MASK) {
    frame_len = dwt_read32bitreg(RX_FINFO_ID) & RX_FINFO_RXFLEN_BIT_MASK;
    if (frame_len <= FRAME_LEN_MAX) {
      dwt_readrxdata(rx_buffer, frame_len - FCS_LEN, 0);

      rx_buffer[ALL_MSG_SN_IDX] = 0;

      if (memcmp(rx_buffer, rx_msg, ALL_MSG_COMMON_LEN) == 0) {
        test_run_info((unsigned char*)"SYNC message Received");
        uint64_t rx_time = dwt_readrxtimestamplo32();
        Serial.print("Received timestamp: ");
        Serial.println(rx_time);
        sendTimestampsToServer("anchor1", rx_time);
        Serial.println("Timestamp Sent");
        tx_to_tag();
      }
    }

    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_RXFCG_BIT_MASK);

  } else {
    dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_ALL_RX_ERR);
  }
}

void tx_to_tag() {
  dwt_writetxdata(FRAME_LENGTH - FCS_LEN, tx_msg, 0); /* Zero offset in TX buffer. */
  dwt_writetxfctrl(FRAME_LENGTH, 0, 0);               /* Zero offset in TX buffer, no ranging. */
  dwt_starttx(DWT_START_TX_IMMEDIATE);
  delay(10);

  while (!(dwt_read32bitreg(SYS_STATUS_ID) & SYS_STATUS_TXFRS_BIT_MASK)) {
    test_run_info((unsigned char*)"WHAT!!!\r\n");
  };

  dwt_write32bitreg(SYS_STATUS_ID, SYS_STATUS_TXFRS_BIT_MASK);

  test_run_info((unsigned char*)"TX Frame Sent to Tag");

  Sleep(TX_DELAY_MS);

  tx_msg[ALL_MSG_SN_IDX]++;
}


void sendTimestampsToServer(const char* role, uint64_t timestamp) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;

    http.begin(serverName);
    http.addHeader("Content-Type", "application/json");

    String payload = "{ \"role\": \"" + String(role) + "\", \"timestamp\": " + String(timestamp) + " }";

    int httpResponseCode = http.POST(payload);

    if (httpResponseCode > 0) {
      String response = http.getString();
    } else {
      Serial.print("Error on sending POST: ");
      Serial.println(httpResponseCode);
    }

    http.end();
  } else {
    Serial.println("Error in WiFi connection");
  }
}