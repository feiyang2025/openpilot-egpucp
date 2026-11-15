#include "pose.h"

namespace {
#define DIM 18
#define EDIM 18
#define MEDIM 18
typedef void (*Hfun)(double *, double *, double *);
const static double MAHA_THRESH_4 = 7.814727903251177;
const static double MAHA_THRESH_10 = 7.814727903251177;
const static double MAHA_THRESH_13 = 7.814727903251177;
const static double MAHA_THRESH_14 = 7.814727903251177;

/******************************************************************************
 *                      Code generated with SymPy 1.14.0                      *
 *                                                                            *
 *              See http://www.sympy.org/ for more information.               *
 *                                                                            *
 *                         This file is part of 'ekf'                         *
 ******************************************************************************/
void err_fun(double *nom_x, double *delta_x, double *out_6219666401814639348) {
   out_6219666401814639348[0] = delta_x[0] + nom_x[0];
   out_6219666401814639348[1] = delta_x[1] + nom_x[1];
   out_6219666401814639348[2] = delta_x[2] + nom_x[2];
   out_6219666401814639348[3] = delta_x[3] + nom_x[3];
   out_6219666401814639348[4] = delta_x[4] + nom_x[4];
   out_6219666401814639348[5] = delta_x[5] + nom_x[5];
   out_6219666401814639348[6] = delta_x[6] + nom_x[6];
   out_6219666401814639348[7] = delta_x[7] + nom_x[7];
   out_6219666401814639348[8] = delta_x[8] + nom_x[8];
   out_6219666401814639348[9] = delta_x[9] + nom_x[9];
   out_6219666401814639348[10] = delta_x[10] + nom_x[10];
   out_6219666401814639348[11] = delta_x[11] + nom_x[11];
   out_6219666401814639348[12] = delta_x[12] + nom_x[12];
   out_6219666401814639348[13] = delta_x[13] + nom_x[13];
   out_6219666401814639348[14] = delta_x[14] + nom_x[14];
   out_6219666401814639348[15] = delta_x[15] + nom_x[15];
   out_6219666401814639348[16] = delta_x[16] + nom_x[16];
   out_6219666401814639348[17] = delta_x[17] + nom_x[17];
}
void inv_err_fun(double *nom_x, double *true_x, double *out_6870330160140080945) {
   out_6870330160140080945[0] = -nom_x[0] + true_x[0];
   out_6870330160140080945[1] = -nom_x[1] + true_x[1];
   out_6870330160140080945[2] = -nom_x[2] + true_x[2];
   out_6870330160140080945[3] = -nom_x[3] + true_x[3];
   out_6870330160140080945[4] = -nom_x[4] + true_x[4];
   out_6870330160140080945[5] = -nom_x[5] + true_x[5];
   out_6870330160140080945[6] = -nom_x[6] + true_x[6];
   out_6870330160140080945[7] = -nom_x[7] + true_x[7];
   out_6870330160140080945[8] = -nom_x[8] + true_x[8];
   out_6870330160140080945[9] = -nom_x[9] + true_x[9];
   out_6870330160140080945[10] = -nom_x[10] + true_x[10];
   out_6870330160140080945[11] = -nom_x[11] + true_x[11];
   out_6870330160140080945[12] = -nom_x[12] + true_x[12];
   out_6870330160140080945[13] = -nom_x[13] + true_x[13];
   out_6870330160140080945[14] = -nom_x[14] + true_x[14];
   out_6870330160140080945[15] = -nom_x[15] + true_x[15];
   out_6870330160140080945[16] = -nom_x[16] + true_x[16];
   out_6870330160140080945[17] = -nom_x[17] + true_x[17];
}
void H_mod_fun(double *state, double *out_1928910883971935919) {
   out_1928910883971935919[0] = 1.0;
   out_1928910883971935919[1] = 0.0;
   out_1928910883971935919[2] = 0.0;
   out_1928910883971935919[3] = 0.0;
   out_1928910883971935919[4] = 0.0;
   out_1928910883971935919[5] = 0.0;
   out_1928910883971935919[6] = 0.0;
   out_1928910883971935919[7] = 0.0;
   out_1928910883971935919[8] = 0.0;
   out_1928910883971935919[9] = 0.0;
   out_1928910883971935919[10] = 0.0;
   out_1928910883971935919[11] = 0.0;
   out_1928910883971935919[12] = 0.0;
   out_1928910883971935919[13] = 0.0;
   out_1928910883971935919[14] = 0.0;
   out_1928910883971935919[15] = 0.0;
   out_1928910883971935919[16] = 0.0;
   out_1928910883971935919[17] = 0.0;
   out_1928910883971935919[18] = 0.0;
   out_1928910883971935919[19] = 1.0;
   out_1928910883971935919[20] = 0.0;
   out_1928910883971935919[21] = 0.0;
   out_1928910883971935919[22] = 0.0;
   out_1928910883971935919[23] = 0.0;
   out_1928910883971935919[24] = 0.0;
   out_1928910883971935919[25] = 0.0;
   out_1928910883971935919[26] = 0.0;
   out_1928910883971935919[27] = 0.0;
   out_1928910883971935919[28] = 0.0;
   out_1928910883971935919[29] = 0.0;
   out_1928910883971935919[30] = 0.0;
   out_1928910883971935919[31] = 0.0;
   out_1928910883971935919[32] = 0.0;
   out_1928910883971935919[33] = 0.0;
   out_1928910883971935919[34] = 0.0;
   out_1928910883971935919[35] = 0.0;
   out_1928910883971935919[36] = 0.0;
   out_1928910883971935919[37] = 0.0;
   out_1928910883971935919[38] = 1.0;
   out_1928910883971935919[39] = 0.0;
   out_1928910883971935919[40] = 0.0;
   out_1928910883971935919[41] = 0.0;
   out_1928910883971935919[42] = 0.0;
   out_1928910883971935919[43] = 0.0;
   out_1928910883971935919[44] = 0.0;
   out_1928910883971935919[45] = 0.0;
   out_1928910883971935919[46] = 0.0;
   out_1928910883971935919[47] = 0.0;
   out_1928910883971935919[48] = 0.0;
   out_1928910883971935919[49] = 0.0;
   out_1928910883971935919[50] = 0.0;
   out_1928910883971935919[51] = 0.0;
   out_1928910883971935919[52] = 0.0;
   out_1928910883971935919[53] = 0.0;
   out_1928910883971935919[54] = 0.0;
   out_1928910883971935919[55] = 0.0;
   out_1928910883971935919[56] = 0.0;
   out_1928910883971935919[57] = 1.0;
   out_1928910883971935919[58] = 0.0;
   out_1928910883971935919[59] = 0.0;
   out_1928910883971935919[60] = 0.0;
   out_1928910883971935919[61] = 0.0;
   out_1928910883971935919[62] = 0.0;
   out_1928910883971935919[63] = 0.0;
   out_1928910883971935919[64] = 0.0;
   out_1928910883971935919[65] = 0.0;
   out_1928910883971935919[66] = 0.0;
   out_1928910883971935919[67] = 0.0;
   out_1928910883971935919[68] = 0.0;
   out_1928910883971935919[69] = 0.0;
   out_1928910883971935919[70] = 0.0;
   out_1928910883971935919[71] = 0.0;
   out_1928910883971935919[72] = 0.0;
   out_1928910883971935919[73] = 0.0;
   out_1928910883971935919[74] = 0.0;
   out_1928910883971935919[75] = 0.0;
   out_1928910883971935919[76] = 1.0;
   out_1928910883971935919[77] = 0.0;
   out_1928910883971935919[78] = 0.0;
   out_1928910883971935919[79] = 0.0;
   out_1928910883971935919[80] = 0.0;
   out_1928910883971935919[81] = 0.0;
   out_1928910883971935919[82] = 0.0;
   out_1928910883971935919[83] = 0.0;
   out_1928910883971935919[84] = 0.0;
   out_1928910883971935919[85] = 0.0;
   out_1928910883971935919[86] = 0.0;
   out_1928910883971935919[87] = 0.0;
   out_1928910883971935919[88] = 0.0;
   out_1928910883971935919[89] = 0.0;
   out_1928910883971935919[90] = 0.0;
   out_1928910883971935919[91] = 0.0;
   out_1928910883971935919[92] = 0.0;
   out_1928910883971935919[93] = 0.0;
   out_1928910883971935919[94] = 0.0;
   out_1928910883971935919[95] = 1.0;
   out_1928910883971935919[96] = 0.0;
   out_1928910883971935919[97] = 0.0;
   out_1928910883971935919[98] = 0.0;
   out_1928910883971935919[99] = 0.0;
   out_1928910883971935919[100] = 0.0;
   out_1928910883971935919[101] = 0.0;
   out_1928910883971935919[102] = 0.0;
   out_1928910883971935919[103] = 0.0;
   out_1928910883971935919[104] = 0.0;
   out_1928910883971935919[105] = 0.0;
   out_1928910883971935919[106] = 0.0;
   out_1928910883971935919[107] = 0.0;
   out_1928910883971935919[108] = 0.0;
   out_1928910883971935919[109] = 0.0;
   out_1928910883971935919[110] = 0.0;
   out_1928910883971935919[111] = 0.0;
   out_1928910883971935919[112] = 0.0;
   out_1928910883971935919[113] = 0.0;
   out_1928910883971935919[114] = 1.0;
   out_1928910883971935919[115] = 0.0;
   out_1928910883971935919[116] = 0.0;
   out_1928910883971935919[117] = 0.0;
   out_1928910883971935919[118] = 0.0;
   out_1928910883971935919[119] = 0.0;
   out_1928910883971935919[120] = 0.0;
   out_1928910883971935919[121] = 0.0;
   out_1928910883971935919[122] = 0.0;
   out_1928910883971935919[123] = 0.0;
   out_1928910883971935919[124] = 0.0;
   out_1928910883971935919[125] = 0.0;
   out_1928910883971935919[126] = 0.0;
   out_1928910883971935919[127] = 0.0;
   out_1928910883971935919[128] = 0.0;
   out_1928910883971935919[129] = 0.0;
   out_1928910883971935919[130] = 0.0;
   out_1928910883971935919[131] = 0.0;
   out_1928910883971935919[132] = 0.0;
   out_1928910883971935919[133] = 1.0;
   out_1928910883971935919[134] = 0.0;
   out_1928910883971935919[135] = 0.0;
   out_1928910883971935919[136] = 0.0;
   out_1928910883971935919[137] = 0.0;
   out_1928910883971935919[138] = 0.0;
   out_1928910883971935919[139] = 0.0;
   out_1928910883971935919[140] = 0.0;
   out_1928910883971935919[141] = 0.0;
   out_1928910883971935919[142] = 0.0;
   out_1928910883971935919[143] = 0.0;
   out_1928910883971935919[144] = 0.0;
   out_1928910883971935919[145] = 0.0;
   out_1928910883971935919[146] = 0.0;
   out_1928910883971935919[147] = 0.0;
   out_1928910883971935919[148] = 0.0;
   out_1928910883971935919[149] = 0.0;
   out_1928910883971935919[150] = 0.0;
   out_1928910883971935919[151] = 0.0;
   out_1928910883971935919[152] = 1.0;
   out_1928910883971935919[153] = 0.0;
   out_1928910883971935919[154] = 0.0;
   out_1928910883971935919[155] = 0.0;
   out_1928910883971935919[156] = 0.0;
   out_1928910883971935919[157] = 0.0;
   out_1928910883971935919[158] = 0.0;
   out_1928910883971935919[159] = 0.0;
   out_1928910883971935919[160] = 0.0;
   out_1928910883971935919[161] = 0.0;
   out_1928910883971935919[162] = 0.0;
   out_1928910883971935919[163] = 0.0;
   out_1928910883971935919[164] = 0.0;
   out_1928910883971935919[165] = 0.0;
   out_1928910883971935919[166] = 0.0;
   out_1928910883971935919[167] = 0.0;
   out_1928910883971935919[168] = 0.0;
   out_1928910883971935919[169] = 0.0;
   out_1928910883971935919[170] = 0.0;
   out_1928910883971935919[171] = 1.0;
   out_1928910883971935919[172] = 0.0;
   out_1928910883971935919[173] = 0.0;
   out_1928910883971935919[174] = 0.0;
   out_1928910883971935919[175] = 0.0;
   out_1928910883971935919[176] = 0.0;
   out_1928910883971935919[177] = 0.0;
   out_1928910883971935919[178] = 0.0;
   out_1928910883971935919[179] = 0.0;
   out_1928910883971935919[180] = 0.0;
   out_1928910883971935919[181] = 0.0;
   out_1928910883971935919[182] = 0.0;
   out_1928910883971935919[183] = 0.0;
   out_1928910883971935919[184] = 0.0;
   out_1928910883971935919[185] = 0.0;
   out_1928910883971935919[186] = 0.0;
   out_1928910883971935919[187] = 0.0;
   out_1928910883971935919[188] = 0.0;
   out_1928910883971935919[189] = 0.0;
   out_1928910883971935919[190] = 1.0;
   out_1928910883971935919[191] = 0.0;
   out_1928910883971935919[192] = 0.0;
   out_1928910883971935919[193] = 0.0;
   out_1928910883971935919[194] = 0.0;
   out_1928910883971935919[195] = 0.0;
   out_1928910883971935919[196] = 0.0;
   out_1928910883971935919[197] = 0.0;
   out_1928910883971935919[198] = 0.0;
   out_1928910883971935919[199] = 0.0;
   out_1928910883971935919[200] = 0.0;
   out_1928910883971935919[201] = 0.0;
   out_1928910883971935919[202] = 0.0;
   out_1928910883971935919[203] = 0.0;
   out_1928910883971935919[204] = 0.0;
   out_1928910883971935919[205] = 0.0;
   out_1928910883971935919[206] = 0.0;
   out_1928910883971935919[207] = 0.0;
   out_1928910883971935919[208] = 0.0;
   out_1928910883971935919[209] = 1.0;
   out_1928910883971935919[210] = 0.0;
   out_1928910883971935919[211] = 0.0;
   out_1928910883971935919[212] = 0.0;
   out_1928910883971935919[213] = 0.0;
   out_1928910883971935919[214] = 0.0;
   out_1928910883971935919[215] = 0.0;
   out_1928910883971935919[216] = 0.0;
   out_1928910883971935919[217] = 0.0;
   out_1928910883971935919[218] = 0.0;
   out_1928910883971935919[219] = 0.0;
   out_1928910883971935919[220] = 0.0;
   out_1928910883971935919[221] = 0.0;
   out_1928910883971935919[222] = 0.0;
   out_1928910883971935919[223] = 0.0;
   out_1928910883971935919[224] = 0.0;
   out_1928910883971935919[225] = 0.0;
   out_1928910883971935919[226] = 0.0;
   out_1928910883971935919[227] = 0.0;
   out_1928910883971935919[228] = 1.0;
   out_1928910883971935919[229] = 0.0;
   out_1928910883971935919[230] = 0.0;
   out_1928910883971935919[231] = 0.0;
   out_1928910883971935919[232] = 0.0;
   out_1928910883971935919[233] = 0.0;
   out_1928910883971935919[234] = 0.0;
   out_1928910883971935919[235] = 0.0;
   out_1928910883971935919[236] = 0.0;
   out_1928910883971935919[237] = 0.0;
   out_1928910883971935919[238] = 0.0;
   out_1928910883971935919[239] = 0.0;
   out_1928910883971935919[240] = 0.0;
   out_1928910883971935919[241] = 0.0;
   out_1928910883971935919[242] = 0.0;
   out_1928910883971935919[243] = 0.0;
   out_1928910883971935919[244] = 0.0;
   out_1928910883971935919[245] = 0.0;
   out_1928910883971935919[246] = 0.0;
   out_1928910883971935919[247] = 1.0;
   out_1928910883971935919[248] = 0.0;
   out_1928910883971935919[249] = 0.0;
   out_1928910883971935919[250] = 0.0;
   out_1928910883971935919[251] = 0.0;
   out_1928910883971935919[252] = 0.0;
   out_1928910883971935919[253] = 0.0;
   out_1928910883971935919[254] = 0.0;
   out_1928910883971935919[255] = 0.0;
   out_1928910883971935919[256] = 0.0;
   out_1928910883971935919[257] = 0.0;
   out_1928910883971935919[258] = 0.0;
   out_1928910883971935919[259] = 0.0;
   out_1928910883971935919[260] = 0.0;
   out_1928910883971935919[261] = 0.0;
   out_1928910883971935919[262] = 0.0;
   out_1928910883971935919[263] = 0.0;
   out_1928910883971935919[264] = 0.0;
   out_1928910883971935919[265] = 0.0;
   out_1928910883971935919[266] = 1.0;
   out_1928910883971935919[267] = 0.0;
   out_1928910883971935919[268] = 0.0;
   out_1928910883971935919[269] = 0.0;
   out_1928910883971935919[270] = 0.0;
   out_1928910883971935919[271] = 0.0;
   out_1928910883971935919[272] = 0.0;
   out_1928910883971935919[273] = 0.0;
   out_1928910883971935919[274] = 0.0;
   out_1928910883971935919[275] = 0.0;
   out_1928910883971935919[276] = 0.0;
   out_1928910883971935919[277] = 0.0;
   out_1928910883971935919[278] = 0.0;
   out_1928910883971935919[279] = 0.0;
   out_1928910883971935919[280] = 0.0;
   out_1928910883971935919[281] = 0.0;
   out_1928910883971935919[282] = 0.0;
   out_1928910883971935919[283] = 0.0;
   out_1928910883971935919[284] = 0.0;
   out_1928910883971935919[285] = 1.0;
   out_1928910883971935919[286] = 0.0;
   out_1928910883971935919[287] = 0.0;
   out_1928910883971935919[288] = 0.0;
   out_1928910883971935919[289] = 0.0;
   out_1928910883971935919[290] = 0.0;
   out_1928910883971935919[291] = 0.0;
   out_1928910883971935919[292] = 0.0;
   out_1928910883971935919[293] = 0.0;
   out_1928910883971935919[294] = 0.0;
   out_1928910883971935919[295] = 0.0;
   out_1928910883971935919[296] = 0.0;
   out_1928910883971935919[297] = 0.0;
   out_1928910883971935919[298] = 0.0;
   out_1928910883971935919[299] = 0.0;
   out_1928910883971935919[300] = 0.0;
   out_1928910883971935919[301] = 0.0;
   out_1928910883971935919[302] = 0.0;
   out_1928910883971935919[303] = 0.0;
   out_1928910883971935919[304] = 1.0;
   out_1928910883971935919[305] = 0.0;
   out_1928910883971935919[306] = 0.0;
   out_1928910883971935919[307] = 0.0;
   out_1928910883971935919[308] = 0.0;
   out_1928910883971935919[309] = 0.0;
   out_1928910883971935919[310] = 0.0;
   out_1928910883971935919[311] = 0.0;
   out_1928910883971935919[312] = 0.0;
   out_1928910883971935919[313] = 0.0;
   out_1928910883971935919[314] = 0.0;
   out_1928910883971935919[315] = 0.0;
   out_1928910883971935919[316] = 0.0;
   out_1928910883971935919[317] = 0.0;
   out_1928910883971935919[318] = 0.0;
   out_1928910883971935919[319] = 0.0;
   out_1928910883971935919[320] = 0.0;
   out_1928910883971935919[321] = 0.0;
   out_1928910883971935919[322] = 0.0;
   out_1928910883971935919[323] = 1.0;
}
void f_fun(double *state, double dt, double *out_8030521232260507982) {
   out_8030521232260507982[0] = atan2((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), -(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]));
   out_8030521232260507982[1] = asin(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]));
   out_8030521232260507982[2] = atan2(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), -(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]));
   out_8030521232260507982[3] = dt*state[12] + state[3];
   out_8030521232260507982[4] = dt*state[13] + state[4];
   out_8030521232260507982[5] = dt*state[14] + state[5];
   out_8030521232260507982[6] = state[6];
   out_8030521232260507982[7] = state[7];
   out_8030521232260507982[8] = state[8];
   out_8030521232260507982[9] = state[9];
   out_8030521232260507982[10] = state[10];
   out_8030521232260507982[11] = state[11];
   out_8030521232260507982[12] = state[12];
   out_8030521232260507982[13] = state[13];
   out_8030521232260507982[14] = state[14];
   out_8030521232260507982[15] = state[15];
   out_8030521232260507982[16] = state[16];
   out_8030521232260507982[17] = state[17];
}
void F_fun(double *state, double dt, double *out_3503743028922815958) {
   out_3503743028922815958[0] = ((-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*cos(state[0])*cos(state[1]) - sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*cos(state[0])*cos(state[1]) - sin(dt*state[6])*sin(state[0])*cos(dt*state[7])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3503743028922815958[1] = ((-sin(dt*state[6])*sin(dt*state[8]) - sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*cos(state[1]) - (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*sin(state[1]) - sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(state[0]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*sin(state[1]) + (-sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) + sin(dt*state[8])*cos(dt*state[6]))*cos(state[1]) - sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(state[0]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3503743028922815958[2] = 0;
   out_3503743028922815958[3] = 0;
   out_3503743028922815958[4] = 0;
   out_3503743028922815958[5] = 0;
   out_3503743028922815958[6] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(dt*cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) - dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3503743028922815958[7] = (-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[6])*sin(dt*state[7])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[6])*sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) - dt*sin(dt*state[6])*sin(state[1])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + (-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))*(-dt*sin(dt*state[7])*cos(dt*state[6])*cos(state[0])*cos(state[1]) + dt*sin(dt*state[8])*sin(state[0])*cos(dt*state[6])*cos(dt*state[7])*cos(state[1]) - dt*sin(state[1])*cos(dt*state[6])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3503743028922815958[8] = ((dt*sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + dt*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (dt*sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]))*(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2)) + ((dt*sin(dt*state[6])*sin(dt*state[8]) + dt*sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (-dt*sin(dt*state[6])*cos(dt*state[8]) + dt*sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]))*(-(sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) + (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) - sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/(pow(-(sin(dt*state[6])*sin(dt*state[8]) + sin(dt*state[7])*cos(dt*state[6])*cos(dt*state[8]))*sin(state[1]) + (-sin(dt*state[6])*cos(dt*state[8]) + sin(dt*state[7])*sin(dt*state[8])*cos(dt*state[6]))*sin(state[0])*cos(state[1]) + cos(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2) + pow((sin(dt*state[6])*sin(dt*state[7])*sin(dt*state[8]) + cos(dt*state[6])*cos(dt*state[8]))*sin(state[0])*cos(state[1]) - (sin(dt*state[6])*sin(dt*state[7])*cos(dt*state[8]) - sin(dt*state[8])*cos(dt*state[6]))*sin(state[1]) + sin(dt*state[6])*cos(dt*state[7])*cos(state[0])*cos(state[1]), 2));
   out_3503743028922815958[9] = 0;
   out_3503743028922815958[10] = 0;
   out_3503743028922815958[11] = 0;
   out_3503743028922815958[12] = 0;
   out_3503743028922815958[13] = 0;
   out_3503743028922815958[14] = 0;
   out_3503743028922815958[15] = 0;
   out_3503743028922815958[16] = 0;
   out_3503743028922815958[17] = 0;
   out_3503743028922815958[18] = (-sin(dt*state[7])*sin(state[0])*cos(state[1]) - sin(dt*state[8])*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_3503743028922815958[19] = (-sin(dt*state[7])*sin(state[1])*cos(state[0]) + sin(dt*state[8])*sin(state[0])*sin(state[1])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_3503743028922815958[20] = 0;
   out_3503743028922815958[21] = 0;
   out_3503743028922815958[22] = 0;
   out_3503743028922815958[23] = 0;
   out_3503743028922815958[24] = 0;
   out_3503743028922815958[25] = (dt*sin(dt*state[7])*sin(dt*state[8])*sin(state[0])*cos(state[1]) - dt*sin(dt*state[7])*sin(state[1])*cos(dt*state[8]) + dt*cos(dt*state[7])*cos(state[0])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_3503743028922815958[26] = (-dt*sin(dt*state[8])*sin(state[1])*cos(dt*state[7]) - dt*sin(state[0])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/sqrt(1 - pow(sin(dt*state[7])*cos(state[0])*cos(state[1]) - sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1]) + sin(state[1])*cos(dt*state[7])*cos(dt*state[8]), 2));
   out_3503743028922815958[27] = 0;
   out_3503743028922815958[28] = 0;
   out_3503743028922815958[29] = 0;
   out_3503743028922815958[30] = 0;
   out_3503743028922815958[31] = 0;
   out_3503743028922815958[32] = 0;
   out_3503743028922815958[33] = 0;
   out_3503743028922815958[34] = 0;
   out_3503743028922815958[35] = 0;
   out_3503743028922815958[36] = ((sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3503743028922815958[37] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-sin(dt*state[7])*sin(state[2])*cos(state[0])*cos(state[1]) + sin(dt*state[8])*sin(state[0])*sin(state[2])*cos(dt*state[7])*cos(state[1]) - sin(state[1])*sin(state[2])*cos(dt*state[7])*cos(dt*state[8]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(-sin(dt*state[7])*cos(state[0])*cos(state[1])*cos(state[2]) + sin(dt*state[8])*sin(state[0])*cos(dt*state[7])*cos(state[1])*cos(state[2]) - sin(state[1])*cos(dt*state[7])*cos(dt*state[8])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3503743028922815958[38] = ((-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (-sin(state[0])*sin(state[1])*sin(state[2]) - cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3503743028922815958[39] = 0;
   out_3503743028922815958[40] = 0;
   out_3503743028922815958[41] = 0;
   out_3503743028922815958[42] = 0;
   out_3503743028922815958[43] = (-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))*(dt*(sin(state[0])*cos(state[2]) - sin(state[1])*sin(state[2])*cos(state[0]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*sin(state[2])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + ((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))*(dt*(-sin(state[0])*sin(state[2]) - sin(state[1])*cos(state[0])*cos(state[2]))*cos(dt*state[7]) - dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[7])*sin(dt*state[8]) - dt*sin(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3503743028922815958[44] = (dt*(sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*sin(state[2])*cos(dt*state[7])*cos(state[1]))*(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2)) + (dt*(sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*cos(dt*state[7])*cos(dt*state[8]) - dt*sin(dt*state[8])*cos(dt*state[7])*cos(state[1])*cos(state[2]))*((-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) - (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) - sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]))/(pow(-(sin(state[0])*sin(state[2]) + sin(state[1])*cos(state[0])*cos(state[2]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*cos(state[2]) - sin(state[2])*cos(state[0]))*sin(dt*state[8])*cos(dt*state[7]) + cos(dt*state[7])*cos(dt*state[8])*cos(state[1])*cos(state[2]), 2) + pow(-(-sin(state[0])*cos(state[2]) + sin(state[1])*sin(state[2])*cos(state[0]))*sin(dt*state[7]) + (sin(state[0])*sin(state[1])*sin(state[2]) + cos(state[0])*cos(state[2]))*sin(dt*state[8])*cos(dt*state[7]) + sin(state[2])*cos(dt*state[7])*cos(dt*state[8])*cos(state[1]), 2));
   out_3503743028922815958[45] = 0;
   out_3503743028922815958[46] = 0;
   out_3503743028922815958[47] = 0;
   out_3503743028922815958[48] = 0;
   out_3503743028922815958[49] = 0;
   out_3503743028922815958[50] = 0;
   out_3503743028922815958[51] = 0;
   out_3503743028922815958[52] = 0;
   out_3503743028922815958[53] = 0;
   out_3503743028922815958[54] = 0;
   out_3503743028922815958[55] = 0;
   out_3503743028922815958[56] = 0;
   out_3503743028922815958[57] = 1;
   out_3503743028922815958[58] = 0;
   out_3503743028922815958[59] = 0;
   out_3503743028922815958[60] = 0;
   out_3503743028922815958[61] = 0;
   out_3503743028922815958[62] = 0;
   out_3503743028922815958[63] = 0;
   out_3503743028922815958[64] = 0;
   out_3503743028922815958[65] = 0;
   out_3503743028922815958[66] = dt;
   out_3503743028922815958[67] = 0;
   out_3503743028922815958[68] = 0;
   out_3503743028922815958[69] = 0;
   out_3503743028922815958[70] = 0;
   out_3503743028922815958[71] = 0;
   out_3503743028922815958[72] = 0;
   out_3503743028922815958[73] = 0;
   out_3503743028922815958[74] = 0;
   out_3503743028922815958[75] = 0;
   out_3503743028922815958[76] = 1;
   out_3503743028922815958[77] = 0;
   out_3503743028922815958[78] = 0;
   out_3503743028922815958[79] = 0;
   out_3503743028922815958[80] = 0;
   out_3503743028922815958[81] = 0;
   out_3503743028922815958[82] = 0;
   out_3503743028922815958[83] = 0;
   out_3503743028922815958[84] = 0;
   out_3503743028922815958[85] = dt;
   out_3503743028922815958[86] = 0;
   out_3503743028922815958[87] = 0;
   out_3503743028922815958[88] = 0;
   out_3503743028922815958[89] = 0;
   out_3503743028922815958[90] = 0;
   out_3503743028922815958[91] = 0;
   out_3503743028922815958[92] = 0;
   out_3503743028922815958[93] = 0;
   out_3503743028922815958[94] = 0;
   out_3503743028922815958[95] = 1;
   out_3503743028922815958[96] = 0;
   out_3503743028922815958[97] = 0;
   out_3503743028922815958[98] = 0;
   out_3503743028922815958[99] = 0;
   out_3503743028922815958[100] = 0;
   out_3503743028922815958[101] = 0;
   out_3503743028922815958[102] = 0;
   out_3503743028922815958[103] = 0;
   out_3503743028922815958[104] = dt;
   out_3503743028922815958[105] = 0;
   out_3503743028922815958[106] = 0;
   out_3503743028922815958[107] = 0;
   out_3503743028922815958[108] = 0;
   out_3503743028922815958[109] = 0;
   out_3503743028922815958[110] = 0;
   out_3503743028922815958[111] = 0;
   out_3503743028922815958[112] = 0;
   out_3503743028922815958[113] = 0;
   out_3503743028922815958[114] = 1;
   out_3503743028922815958[115] = 0;
   out_3503743028922815958[116] = 0;
   out_3503743028922815958[117] = 0;
   out_3503743028922815958[118] = 0;
   out_3503743028922815958[119] = 0;
   out_3503743028922815958[120] = 0;
   out_3503743028922815958[121] = 0;
   out_3503743028922815958[122] = 0;
   out_3503743028922815958[123] = 0;
   out_3503743028922815958[124] = 0;
   out_3503743028922815958[125] = 0;
   out_3503743028922815958[126] = 0;
   out_3503743028922815958[127] = 0;
   out_3503743028922815958[128] = 0;
   out_3503743028922815958[129] = 0;
   out_3503743028922815958[130] = 0;
   out_3503743028922815958[131] = 0;
   out_3503743028922815958[132] = 0;
   out_3503743028922815958[133] = 1;
   out_3503743028922815958[134] = 0;
   out_3503743028922815958[135] = 0;
   out_3503743028922815958[136] = 0;
   out_3503743028922815958[137] = 0;
   out_3503743028922815958[138] = 0;
   out_3503743028922815958[139] = 0;
   out_3503743028922815958[140] = 0;
   out_3503743028922815958[141] = 0;
   out_3503743028922815958[142] = 0;
   out_3503743028922815958[143] = 0;
   out_3503743028922815958[144] = 0;
   out_3503743028922815958[145] = 0;
   out_3503743028922815958[146] = 0;
   out_3503743028922815958[147] = 0;
   out_3503743028922815958[148] = 0;
   out_3503743028922815958[149] = 0;
   out_3503743028922815958[150] = 0;
   out_3503743028922815958[151] = 0;
   out_3503743028922815958[152] = 1;
   out_3503743028922815958[153] = 0;
   out_3503743028922815958[154] = 0;
   out_3503743028922815958[155] = 0;
   out_3503743028922815958[156] = 0;
   out_3503743028922815958[157] = 0;
   out_3503743028922815958[158] = 0;
   out_3503743028922815958[159] = 0;
   out_3503743028922815958[160] = 0;
   out_3503743028922815958[161] = 0;
   out_3503743028922815958[162] = 0;
   out_3503743028922815958[163] = 0;
   out_3503743028922815958[164] = 0;
   out_3503743028922815958[165] = 0;
   out_3503743028922815958[166] = 0;
   out_3503743028922815958[167] = 0;
   out_3503743028922815958[168] = 0;
   out_3503743028922815958[169] = 0;
   out_3503743028922815958[170] = 0;
   out_3503743028922815958[171] = 1;
   out_3503743028922815958[172] = 0;
   out_3503743028922815958[173] = 0;
   out_3503743028922815958[174] = 0;
   out_3503743028922815958[175] = 0;
   out_3503743028922815958[176] = 0;
   out_3503743028922815958[177] = 0;
   out_3503743028922815958[178] = 0;
   out_3503743028922815958[179] = 0;
   out_3503743028922815958[180] = 0;
   out_3503743028922815958[181] = 0;
   out_3503743028922815958[182] = 0;
   out_3503743028922815958[183] = 0;
   out_3503743028922815958[184] = 0;
   out_3503743028922815958[185] = 0;
   out_3503743028922815958[186] = 0;
   out_3503743028922815958[187] = 0;
   out_3503743028922815958[188] = 0;
   out_3503743028922815958[189] = 0;
   out_3503743028922815958[190] = 1;
   out_3503743028922815958[191] = 0;
   out_3503743028922815958[192] = 0;
   out_3503743028922815958[193] = 0;
   out_3503743028922815958[194] = 0;
   out_3503743028922815958[195] = 0;
   out_3503743028922815958[196] = 0;
   out_3503743028922815958[197] = 0;
   out_3503743028922815958[198] = 0;
   out_3503743028922815958[199] = 0;
   out_3503743028922815958[200] = 0;
   out_3503743028922815958[201] = 0;
   out_3503743028922815958[202] = 0;
   out_3503743028922815958[203] = 0;
   out_3503743028922815958[204] = 0;
   out_3503743028922815958[205] = 0;
   out_3503743028922815958[206] = 0;
   out_3503743028922815958[207] = 0;
   out_3503743028922815958[208] = 0;
   out_3503743028922815958[209] = 1;
   out_3503743028922815958[210] = 0;
   out_3503743028922815958[211] = 0;
   out_3503743028922815958[212] = 0;
   out_3503743028922815958[213] = 0;
   out_3503743028922815958[214] = 0;
   out_3503743028922815958[215] = 0;
   out_3503743028922815958[216] = 0;
   out_3503743028922815958[217] = 0;
   out_3503743028922815958[218] = 0;
   out_3503743028922815958[219] = 0;
   out_3503743028922815958[220] = 0;
   out_3503743028922815958[221] = 0;
   out_3503743028922815958[222] = 0;
   out_3503743028922815958[223] = 0;
   out_3503743028922815958[224] = 0;
   out_3503743028922815958[225] = 0;
   out_3503743028922815958[226] = 0;
   out_3503743028922815958[227] = 0;
   out_3503743028922815958[228] = 1;
   out_3503743028922815958[229] = 0;
   out_3503743028922815958[230] = 0;
   out_3503743028922815958[231] = 0;
   out_3503743028922815958[232] = 0;
   out_3503743028922815958[233] = 0;
   out_3503743028922815958[234] = 0;
   out_3503743028922815958[235] = 0;
   out_3503743028922815958[236] = 0;
   out_3503743028922815958[237] = 0;
   out_3503743028922815958[238] = 0;
   out_3503743028922815958[239] = 0;
   out_3503743028922815958[240] = 0;
   out_3503743028922815958[241] = 0;
   out_3503743028922815958[242] = 0;
   out_3503743028922815958[243] = 0;
   out_3503743028922815958[244] = 0;
   out_3503743028922815958[245] = 0;
   out_3503743028922815958[246] = 0;
   out_3503743028922815958[247] = 1;
   out_3503743028922815958[248] = 0;
   out_3503743028922815958[249] = 0;
   out_3503743028922815958[250] = 0;
   out_3503743028922815958[251] = 0;
   out_3503743028922815958[252] = 0;
   out_3503743028922815958[253] = 0;
   out_3503743028922815958[254] = 0;
   out_3503743028922815958[255] = 0;
   out_3503743028922815958[256] = 0;
   out_3503743028922815958[257] = 0;
   out_3503743028922815958[258] = 0;
   out_3503743028922815958[259] = 0;
   out_3503743028922815958[260] = 0;
   out_3503743028922815958[261] = 0;
   out_3503743028922815958[262] = 0;
   out_3503743028922815958[263] = 0;
   out_3503743028922815958[264] = 0;
   out_3503743028922815958[265] = 0;
   out_3503743028922815958[266] = 1;
   out_3503743028922815958[267] = 0;
   out_3503743028922815958[268] = 0;
   out_3503743028922815958[269] = 0;
   out_3503743028922815958[270] = 0;
   out_3503743028922815958[271] = 0;
   out_3503743028922815958[272] = 0;
   out_3503743028922815958[273] = 0;
   out_3503743028922815958[274] = 0;
   out_3503743028922815958[275] = 0;
   out_3503743028922815958[276] = 0;
   out_3503743028922815958[277] = 0;
   out_3503743028922815958[278] = 0;
   out_3503743028922815958[279] = 0;
   out_3503743028922815958[280] = 0;
   out_3503743028922815958[281] = 0;
   out_3503743028922815958[282] = 0;
   out_3503743028922815958[283] = 0;
   out_3503743028922815958[284] = 0;
   out_3503743028922815958[285] = 1;
   out_3503743028922815958[286] = 0;
   out_3503743028922815958[287] = 0;
   out_3503743028922815958[288] = 0;
   out_3503743028922815958[289] = 0;
   out_3503743028922815958[290] = 0;
   out_3503743028922815958[291] = 0;
   out_3503743028922815958[292] = 0;
   out_3503743028922815958[293] = 0;
   out_3503743028922815958[294] = 0;
   out_3503743028922815958[295] = 0;
   out_3503743028922815958[296] = 0;
   out_3503743028922815958[297] = 0;
   out_3503743028922815958[298] = 0;
   out_3503743028922815958[299] = 0;
   out_3503743028922815958[300] = 0;
   out_3503743028922815958[301] = 0;
   out_3503743028922815958[302] = 0;
   out_3503743028922815958[303] = 0;
   out_3503743028922815958[304] = 1;
   out_3503743028922815958[305] = 0;
   out_3503743028922815958[306] = 0;
   out_3503743028922815958[307] = 0;
   out_3503743028922815958[308] = 0;
   out_3503743028922815958[309] = 0;
   out_3503743028922815958[310] = 0;
   out_3503743028922815958[311] = 0;
   out_3503743028922815958[312] = 0;
   out_3503743028922815958[313] = 0;
   out_3503743028922815958[314] = 0;
   out_3503743028922815958[315] = 0;
   out_3503743028922815958[316] = 0;
   out_3503743028922815958[317] = 0;
   out_3503743028922815958[318] = 0;
   out_3503743028922815958[319] = 0;
   out_3503743028922815958[320] = 0;
   out_3503743028922815958[321] = 0;
   out_3503743028922815958[322] = 0;
   out_3503743028922815958[323] = 1;
}
void h_4(double *state, double *unused, double *out_5552913628623474626) {
   out_5552913628623474626[0] = state[6] + state[9];
   out_5552913628623474626[1] = state[7] + state[10];
   out_5552913628623474626[2] = state[8] + state[11];
}
void H_4(double *state, double *unused, double *out_527442235044937530) {
   out_527442235044937530[0] = 0;
   out_527442235044937530[1] = 0;
   out_527442235044937530[2] = 0;
   out_527442235044937530[3] = 0;
   out_527442235044937530[4] = 0;
   out_527442235044937530[5] = 0;
   out_527442235044937530[6] = 1;
   out_527442235044937530[7] = 0;
   out_527442235044937530[8] = 0;
   out_527442235044937530[9] = 1;
   out_527442235044937530[10] = 0;
   out_527442235044937530[11] = 0;
   out_527442235044937530[12] = 0;
   out_527442235044937530[13] = 0;
   out_527442235044937530[14] = 0;
   out_527442235044937530[15] = 0;
   out_527442235044937530[16] = 0;
   out_527442235044937530[17] = 0;
   out_527442235044937530[18] = 0;
   out_527442235044937530[19] = 0;
   out_527442235044937530[20] = 0;
   out_527442235044937530[21] = 0;
   out_527442235044937530[22] = 0;
   out_527442235044937530[23] = 0;
   out_527442235044937530[24] = 0;
   out_527442235044937530[25] = 1;
   out_527442235044937530[26] = 0;
   out_527442235044937530[27] = 0;
   out_527442235044937530[28] = 1;
   out_527442235044937530[29] = 0;
   out_527442235044937530[30] = 0;
   out_527442235044937530[31] = 0;
   out_527442235044937530[32] = 0;
   out_527442235044937530[33] = 0;
   out_527442235044937530[34] = 0;
   out_527442235044937530[35] = 0;
   out_527442235044937530[36] = 0;
   out_527442235044937530[37] = 0;
   out_527442235044937530[38] = 0;
   out_527442235044937530[39] = 0;
   out_527442235044937530[40] = 0;
   out_527442235044937530[41] = 0;
   out_527442235044937530[42] = 0;
   out_527442235044937530[43] = 0;
   out_527442235044937530[44] = 1;
   out_527442235044937530[45] = 0;
   out_527442235044937530[46] = 0;
   out_527442235044937530[47] = 1;
   out_527442235044937530[48] = 0;
   out_527442235044937530[49] = 0;
   out_527442235044937530[50] = 0;
   out_527442235044937530[51] = 0;
   out_527442235044937530[52] = 0;
   out_527442235044937530[53] = 0;
}
void h_10(double *state, double *unused, double *out_249315959449796468) {
   out_249315959449796468[0] = 9.8100000000000005*sin(state[1]) - state[4]*state[8] + state[5]*state[7] + state[12] + state[15];
   out_249315959449796468[1] = -9.8100000000000005*sin(state[0])*cos(state[1]) + state[3]*state[8] - state[5]*state[6] + state[13] + state[16];
   out_249315959449796468[2] = -9.8100000000000005*cos(state[0])*cos(state[1]) - state[3]*state[7] + state[4]*state[6] + state[14] + state[17];
}
void H_10(double *state, double *unused, double *out_7948841605243004373) {
   out_7948841605243004373[0] = 0;
   out_7948841605243004373[1] = 9.8100000000000005*cos(state[1]);
   out_7948841605243004373[2] = 0;
   out_7948841605243004373[3] = 0;
   out_7948841605243004373[4] = -state[8];
   out_7948841605243004373[5] = state[7];
   out_7948841605243004373[6] = 0;
   out_7948841605243004373[7] = state[5];
   out_7948841605243004373[8] = -state[4];
   out_7948841605243004373[9] = 0;
   out_7948841605243004373[10] = 0;
   out_7948841605243004373[11] = 0;
   out_7948841605243004373[12] = 1;
   out_7948841605243004373[13] = 0;
   out_7948841605243004373[14] = 0;
   out_7948841605243004373[15] = 1;
   out_7948841605243004373[16] = 0;
   out_7948841605243004373[17] = 0;
   out_7948841605243004373[18] = -9.8100000000000005*cos(state[0])*cos(state[1]);
   out_7948841605243004373[19] = 9.8100000000000005*sin(state[0])*sin(state[1]);
   out_7948841605243004373[20] = 0;
   out_7948841605243004373[21] = state[8];
   out_7948841605243004373[22] = 0;
   out_7948841605243004373[23] = -state[6];
   out_7948841605243004373[24] = -state[5];
   out_7948841605243004373[25] = 0;
   out_7948841605243004373[26] = state[3];
   out_7948841605243004373[27] = 0;
   out_7948841605243004373[28] = 0;
   out_7948841605243004373[29] = 0;
   out_7948841605243004373[30] = 0;
   out_7948841605243004373[31] = 1;
   out_7948841605243004373[32] = 0;
   out_7948841605243004373[33] = 0;
   out_7948841605243004373[34] = 1;
   out_7948841605243004373[35] = 0;
   out_7948841605243004373[36] = 9.8100000000000005*sin(state[0])*cos(state[1]);
   out_7948841605243004373[37] = 9.8100000000000005*sin(state[1])*cos(state[0]);
   out_7948841605243004373[38] = 0;
   out_7948841605243004373[39] = -state[7];
   out_7948841605243004373[40] = state[6];
   out_7948841605243004373[41] = 0;
   out_7948841605243004373[42] = state[4];
   out_7948841605243004373[43] = -state[3];
   out_7948841605243004373[44] = 0;
   out_7948841605243004373[45] = 0;
   out_7948841605243004373[46] = 0;
   out_7948841605243004373[47] = 0;
   out_7948841605243004373[48] = 0;
   out_7948841605243004373[49] = 0;
   out_7948841605243004373[50] = 1;
   out_7948841605243004373[51] = 0;
   out_7948841605243004373[52] = 0;
   out_7948841605243004373[53] = 1;
}
void h_13(double *state, double *unused, double *out_2639064768667693187) {
   out_2639064768667693187[0] = state[3];
   out_2639064768667693187[1] = state[4];
   out_2639064768667693187[2] = state[5];
}
void H_13(double *state, double *unused, double *out_3739716060377270331) {
   out_3739716060377270331[0] = 0;
   out_3739716060377270331[1] = 0;
   out_3739716060377270331[2] = 0;
   out_3739716060377270331[3] = 1;
   out_3739716060377270331[4] = 0;
   out_3739716060377270331[5] = 0;
   out_3739716060377270331[6] = 0;
   out_3739716060377270331[7] = 0;
   out_3739716060377270331[8] = 0;
   out_3739716060377270331[9] = 0;
   out_3739716060377270331[10] = 0;
   out_3739716060377270331[11] = 0;
   out_3739716060377270331[12] = 0;
   out_3739716060377270331[13] = 0;
   out_3739716060377270331[14] = 0;
   out_3739716060377270331[15] = 0;
   out_3739716060377270331[16] = 0;
   out_3739716060377270331[17] = 0;
   out_3739716060377270331[18] = 0;
   out_3739716060377270331[19] = 0;
   out_3739716060377270331[20] = 0;
   out_3739716060377270331[21] = 0;
   out_3739716060377270331[22] = 1;
   out_3739716060377270331[23] = 0;
   out_3739716060377270331[24] = 0;
   out_3739716060377270331[25] = 0;
   out_3739716060377270331[26] = 0;
   out_3739716060377270331[27] = 0;
   out_3739716060377270331[28] = 0;
   out_3739716060377270331[29] = 0;
   out_3739716060377270331[30] = 0;
   out_3739716060377270331[31] = 0;
   out_3739716060377270331[32] = 0;
   out_3739716060377270331[33] = 0;
   out_3739716060377270331[34] = 0;
   out_3739716060377270331[35] = 0;
   out_3739716060377270331[36] = 0;
   out_3739716060377270331[37] = 0;
   out_3739716060377270331[38] = 0;
   out_3739716060377270331[39] = 0;
   out_3739716060377270331[40] = 0;
   out_3739716060377270331[41] = 1;
   out_3739716060377270331[42] = 0;
   out_3739716060377270331[43] = 0;
   out_3739716060377270331[44] = 0;
   out_3739716060377270331[45] = 0;
   out_3739716060377270331[46] = 0;
   out_3739716060377270331[47] = 0;
   out_3739716060377270331[48] = 0;
   out_3739716060377270331[49] = 0;
   out_3739716060377270331[50] = 0;
   out_3739716060377270331[51] = 0;
   out_3739716060377270331[52] = 0;
   out_3739716060377270331[53] = 0;
}
void h_14(double *state, double *unused, double *out_3162521539941766119) {
   out_3162521539941766119[0] = state[6];
   out_3162521539941766119[1] = state[7];
   out_3162521539941766119[2] = state[8];
}
void H_14(double *state, double *unused, double *out_4490683091384422059) {
   out_4490683091384422059[0] = 0;
   out_4490683091384422059[1] = 0;
   out_4490683091384422059[2] = 0;
   out_4490683091384422059[3] = 0;
   out_4490683091384422059[4] = 0;
   out_4490683091384422059[5] = 0;
   out_4490683091384422059[6] = 1;
   out_4490683091384422059[7] = 0;
   out_4490683091384422059[8] = 0;
   out_4490683091384422059[9] = 0;
   out_4490683091384422059[10] = 0;
   out_4490683091384422059[11] = 0;
   out_4490683091384422059[12] = 0;
   out_4490683091384422059[13] = 0;
   out_4490683091384422059[14] = 0;
   out_4490683091384422059[15] = 0;
   out_4490683091384422059[16] = 0;
   out_4490683091384422059[17] = 0;
   out_4490683091384422059[18] = 0;
   out_4490683091384422059[19] = 0;
   out_4490683091384422059[20] = 0;
   out_4490683091384422059[21] = 0;
   out_4490683091384422059[22] = 0;
   out_4490683091384422059[23] = 0;
   out_4490683091384422059[24] = 0;
   out_4490683091384422059[25] = 1;
   out_4490683091384422059[26] = 0;
   out_4490683091384422059[27] = 0;
   out_4490683091384422059[28] = 0;
   out_4490683091384422059[29] = 0;
   out_4490683091384422059[30] = 0;
   out_4490683091384422059[31] = 0;
   out_4490683091384422059[32] = 0;
   out_4490683091384422059[33] = 0;
   out_4490683091384422059[34] = 0;
   out_4490683091384422059[35] = 0;
   out_4490683091384422059[36] = 0;
   out_4490683091384422059[37] = 0;
   out_4490683091384422059[38] = 0;
   out_4490683091384422059[39] = 0;
   out_4490683091384422059[40] = 0;
   out_4490683091384422059[41] = 0;
   out_4490683091384422059[42] = 0;
   out_4490683091384422059[43] = 0;
   out_4490683091384422059[44] = 1;
   out_4490683091384422059[45] = 0;
   out_4490683091384422059[46] = 0;
   out_4490683091384422059[47] = 0;
   out_4490683091384422059[48] = 0;
   out_4490683091384422059[49] = 0;
   out_4490683091384422059[50] = 0;
   out_4490683091384422059[51] = 0;
   out_4490683091384422059[52] = 0;
   out_4490683091384422059[53] = 0;
}
#include <eigen3/Eigen/Dense>
#include <iostream>

typedef Eigen::Matrix<double, DIM, DIM, Eigen::RowMajor> DDM;
typedef Eigen::Matrix<double, EDIM, EDIM, Eigen::RowMajor> EEM;
typedef Eigen::Matrix<double, DIM, EDIM, Eigen::RowMajor> DEM;

void predict(double *in_x, double *in_P, double *in_Q, double dt) {
  typedef Eigen::Matrix<double, MEDIM, MEDIM, Eigen::RowMajor> RRM;

  double nx[DIM] = {0};
  double in_F[EDIM*EDIM] = {0};

  // functions from sympy
  f_fun(in_x, dt, nx);
  F_fun(in_x, dt, in_F);


  EEM F(in_F);
  EEM P(in_P);
  EEM Q(in_Q);

  RRM F_main = F.topLeftCorner(MEDIM, MEDIM);
  P.topLeftCorner(MEDIM, MEDIM) = (F_main * P.topLeftCorner(MEDIM, MEDIM)) * F_main.transpose();
  P.topRightCorner(MEDIM, EDIM - MEDIM) = F_main * P.topRightCorner(MEDIM, EDIM - MEDIM);
  P.bottomLeftCorner(EDIM - MEDIM, MEDIM) = P.bottomLeftCorner(EDIM - MEDIM, MEDIM) * F_main.transpose();

  P = P + dt*Q;

  // copy out state
  memcpy(in_x, nx, DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
}

// note: extra_args dim only correct when null space projecting
// otherwise 1
template <int ZDIM, int EADIM, bool MAHA_TEST>
void update(double *in_x, double *in_P, Hfun h_fun, Hfun H_fun, Hfun Hea_fun, double *in_z, double *in_R, double *in_ea, double MAHA_THRESHOLD) {
  typedef Eigen::Matrix<double, ZDIM, ZDIM, Eigen::RowMajor> ZZM;
  typedef Eigen::Matrix<double, ZDIM, DIM, Eigen::RowMajor> ZDM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, EDIM, Eigen::RowMajor> XEM;
  //typedef Eigen::Matrix<double, EDIM, ZDIM, Eigen::RowMajor> EZM;
  typedef Eigen::Matrix<double, Eigen::Dynamic, 1> X1M;
  typedef Eigen::Matrix<double, Eigen::Dynamic, Eigen::Dynamic, Eigen::RowMajor> XXM;

  double in_hx[ZDIM] = {0};
  double in_H[ZDIM * DIM] = {0};
  double in_H_mod[EDIM * DIM] = {0};
  double delta_x[EDIM] = {0};
  double x_new[DIM] = {0};


  // state x, P
  Eigen::Matrix<double, ZDIM, 1> z(in_z);
  EEM P(in_P);
  ZZM pre_R(in_R);

  // functions from sympy
  h_fun(in_x, in_ea, in_hx);
  H_fun(in_x, in_ea, in_H);
  ZDM pre_H(in_H);

  // get y (y = z - hx)
  Eigen::Matrix<double, ZDIM, 1> pre_y(in_hx); pre_y = z - pre_y;
  X1M y; XXM H; XXM R;
  if (Hea_fun){
    typedef Eigen::Matrix<double, ZDIM, EADIM, Eigen::RowMajor> ZAM;
    double in_Hea[ZDIM * EADIM] = {0};
    Hea_fun(in_x, in_ea, in_Hea);
    ZAM Hea(in_Hea);
    XXM A = Hea.transpose().fullPivLu().kernel();


    y = A.transpose() * pre_y;
    H = A.transpose() * pre_H;
    R = A.transpose() * pre_R * A;
  } else {
    y = pre_y;
    H = pre_H;
    R = pre_R;
  }
  // get modified H
  H_mod_fun(in_x, in_H_mod);
  DEM H_mod(in_H_mod);
  XEM H_err = H * H_mod;

  // Do mahalobis distance test
  if (MAHA_TEST){
    XXM a = (H_err * P * H_err.transpose() + R).inverse();
    double maha_dist = y.transpose() * a * y;
    if (maha_dist > MAHA_THRESHOLD){
      R = 1.0e16 * R;
    }
  }

  // Outlier resilient weighting
  double weight = 1;//(1.5)/(1 + y.squaredNorm()/R.sum());

  // kalman gains and I_KH
  XXM S = ((H_err * P) * H_err.transpose()) + R/weight;
  XEM KT = S.fullPivLu().solve(H_err * P.transpose());
  //EZM K = KT.transpose(); TODO: WHY DOES THIS NOT COMPILE?
  //EZM K = S.fullPivLu().solve(H_err * P.transpose()).transpose();
  //std::cout << "Here is the matrix rot:\n" << K << std::endl;
  EEM I_KH = Eigen::Matrix<double, EDIM, EDIM>::Identity() - (KT.transpose() * H_err);

  // update state by injecting dx
  Eigen::Matrix<double, EDIM, 1> dx(delta_x);
  dx  = (KT.transpose() * y);
  memcpy(delta_x, dx.data(), EDIM * sizeof(double));
  err_fun(in_x, delta_x, x_new);
  Eigen::Matrix<double, DIM, 1> x(x_new);

  // update cov
  P = ((I_KH * P) * I_KH.transpose()) + ((KT.transpose() * R) * KT);

  // copy out state
  memcpy(in_x, x.data(), DIM * sizeof(double));
  memcpy(in_P, P.data(), EDIM * EDIM * sizeof(double));
  memcpy(in_z, y.data(), y.rows() * sizeof(double));
}




}
extern "C" {

void pose_update_4(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_4, H_4, NULL, in_z, in_R, in_ea, MAHA_THRESH_4);
}
void pose_update_10(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_10, H_10, NULL, in_z, in_R, in_ea, MAHA_THRESH_10);
}
void pose_update_13(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_13, H_13, NULL, in_z, in_R, in_ea, MAHA_THRESH_13);
}
void pose_update_14(double *in_x, double *in_P, double *in_z, double *in_R, double *in_ea) {
  update<3, 3, 0>(in_x, in_P, h_14, H_14, NULL, in_z, in_R, in_ea, MAHA_THRESH_14);
}
void pose_err_fun(double *nom_x, double *delta_x, double *out_6219666401814639348) {
  err_fun(nom_x, delta_x, out_6219666401814639348);
}
void pose_inv_err_fun(double *nom_x, double *true_x, double *out_6870330160140080945) {
  inv_err_fun(nom_x, true_x, out_6870330160140080945);
}
void pose_H_mod_fun(double *state, double *out_1928910883971935919) {
  H_mod_fun(state, out_1928910883971935919);
}
void pose_f_fun(double *state, double dt, double *out_8030521232260507982) {
  f_fun(state,  dt, out_8030521232260507982);
}
void pose_F_fun(double *state, double dt, double *out_3503743028922815958) {
  F_fun(state,  dt, out_3503743028922815958);
}
void pose_h_4(double *state, double *unused, double *out_5552913628623474626) {
  h_4(state, unused, out_5552913628623474626);
}
void pose_H_4(double *state, double *unused, double *out_527442235044937530) {
  H_4(state, unused, out_527442235044937530);
}
void pose_h_10(double *state, double *unused, double *out_249315959449796468) {
  h_10(state, unused, out_249315959449796468);
}
void pose_H_10(double *state, double *unused, double *out_7948841605243004373) {
  H_10(state, unused, out_7948841605243004373);
}
void pose_h_13(double *state, double *unused, double *out_2639064768667693187) {
  h_13(state, unused, out_2639064768667693187);
}
void pose_H_13(double *state, double *unused, double *out_3739716060377270331) {
  H_13(state, unused, out_3739716060377270331);
}
void pose_h_14(double *state, double *unused, double *out_3162521539941766119) {
  h_14(state, unused, out_3162521539941766119);
}
void pose_H_14(double *state, double *unused, double *out_4490683091384422059) {
  H_14(state, unused, out_4490683091384422059);
}
void pose_predict(double *in_x, double *in_P, double *in_Q, double dt) {
  predict(in_x, in_P, in_Q, dt);
}
}

const EKF pose = {
  .name = "pose",
  .kinds = { 4, 10, 13, 14 },
  .feature_kinds = {  },
  .f_fun = pose_f_fun,
  .F_fun = pose_F_fun,
  .err_fun = pose_err_fun,
  .inv_err_fun = pose_inv_err_fun,
  .H_mod_fun = pose_H_mod_fun,
  .predict = pose_predict,
  .hs = {
    { 4, pose_h_4 },
    { 10, pose_h_10 },
    { 13, pose_h_13 },
    { 14, pose_h_14 },
  },
  .Hs = {
    { 4, pose_H_4 },
    { 10, pose_H_10 },
    { 13, pose_H_13 },
    { 14, pose_H_14 },
  },
  .updates = {
    { 4, pose_update_4 },
    { 10, pose_update_10 },
    { 13, pose_update_13 },
    { 14, pose_update_14 },
  },
  .Hes = {
  },
  .sets = {
  },
  .extra_routines = {
  },
};

ekf_lib_init(pose)
